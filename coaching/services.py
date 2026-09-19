import hashlib
import json
import uuid
from datetime import timedelta,date
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max,Q
from django.utils import timezone
from core import models as m
from core import services as core
from .context import build_context,local_now
from .models import Job,Analysis,Suggestion
from .providers import ProviderError
from .router import route
from .triggers import evaluate
from .push import notify
from .validation import validate_change

def enqueue(user,task,payload=None,dedupe=None):
    return Job.objects.get_or_create(dedupe=dedupe or str(uuid.uuid4()),defaults={'user':user,'task':task,'payload':payload or {}})[0]

def daily(user,reanalyze=False):
    today=local_now(user).date()
    return enqueue(user,'daily',{'date':str(today)},None if reanalyze else f'daily:{user.pk}:{today}')

def on_body_saved(user):
    context=build_context(user,'body')
    triggers=evaluate(context)
    if triggers:
        # One body/recovery analysis per local date; individual noisy entries cannot incur repeated requests.
        return enqueue(user,'body',{'triggers':triggers},f'body:{user.pk}:{local_now(user).date()}')

def food_snapshot(entry):
    from decimal import Decimal
    fields=('name','quantity','calories','protein','carbs','fat','fiber','sugar','sodium','note','state','image')
    nutrients={'calories','protein','carbs','fat','fiber','sugar','sodium'}
    values={k:str(Decimal(str(getattr(entry,k))).normalize()) if k in nutrients and getattr(entry,k) is not None else str(getattr(entry,k)) for k in fields}
    return hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()

def enqueue_food(user,entry):
    if not entry.image: raise ValidationError('This entry has no retained photograph.')
    return enqueue(user,'food',{'entry':str(entry.pk),'snapshot':food_snapshot(entry)})

def exercise_snapshot(exercise):
    fields=('name','activity_type','equipment','aliases','primary_muscles','secondary_muscles','classification')
    return hashlib.sha256(json.dumps({k:getattr(exercise,k) for k in fields},sort_keys=True).encode()).hexdigest()

def enqueue_exercise(user,exercise):
    if exercise.user_id!=user.pk: raise ValidationError('Unknown exercise.')
    if exercise.aliases and exercise.primary_muscles and exercise.classification:
        return None
    return enqueue(user,'exercise',{'exercise':str(exercise.pk),'snapshot':exercise_snapshot(exercise)},f'exercise:{exercise.pk}:{exercise_snapshot(exercise)}')

@transaction.atomic
def decide(user,suggestion_id,accept):
    s=Suggestion.objects.select_for_update().get(pk=suggestion_id,user=user)
    if s.decision!='pending': raise ValidationError('This suggestion has already been decided.')
    if accept:
        validate_change(user,{'kind':s.kind,'before':s.before,'proposed':s.proposed})
        active=core.active_target(user) if s.kind=='nutrition' else core.active_plan(user)
        if not active: raise ValidationError('No active version remains.')
        payload=core.target_payload(active) if s.kind=='nutrition' else core.plan_payload(active)
        if not active or active.version!=s.expected_version or json.loads(json.dumps(payload,default=str))!=s.before:
            raise ValidationError('Current version changed. Request a new analysis before accepting.')
        creator=core.create_target if s.kind=='nutrition' else core.create_plan
        creator(user,s.proposed,reason=s.reason,expected_version=s.expected_version)
    s.decision='accepted' if accept else 'rejected';s.decided_at=timezone.now();s.save()
    return s

def schedule(now=None):
    now=now or timezone.now()
    from zoneinfo import ZoneInfo
    for profile in m.Profile.objects.select_related('user'):
        try:
            local=now.astimezone(ZoneInfo(profile.timezone))
            configured_time=profile.summary_time
            if isinstance(configured_time,str):
                from datetime import time
                configured_time=time.fromisoformat(configured_time)
        except (ValueError,KeyError):
            continue
        if local.time().replace(tzinfo=None)>=configured_time:
            enqueue(profile.user,'daily',{'date':str(local.date())},f'daily:{profile.user_id}:{local.date()}')
        on_body_saved(profile.user)

@transaction.atomic
def claim_job():
    now=timezone.now()
    eligible=Job.objects.filter(Q(status='pending')|Q(status='running',lease_until__lt=now)).order_by('created_at')
    # Compare-and-swap also protects development SQLite; PostgreSQL row locks serialize workers.
    for job in eligible[:10]:
        updated=Job.objects.filter(pk=job.pk,status=job.status,lease_until=job.lease_until).update(status='running',lease_until=now+timedelta(minutes=8),attempts=job.attempts+1)
        if updated:
            job.refresh_from_db()
            if job.attempts>3:
                job.status='failed';job.error='Worker interrupted repeatedly; retry manually.';job.save();continue
            return job

def run_job(job):
    try:
        day=date.fromisoformat(job.payload['date']) if 'date' in job.payload else local_now(job.user).date()
        context=build_context(job.user,job.task,day) if job.task!='exercise' else {}
        prompt=job.payload.get('message','')
        image=None
        if job.task=='body': prompt=json.dumps(job.payload.get('triggers',[]))
        if job.task=='food':
            entry=m.FoodEntry.objects.get(pk=job.payload['entry'],user=job.user)
            if not entry.image: raise ProviderError('image_expired',False)
            from PIL import Image
            from io import BytesIO
            from django.conf import settings
            from pathlib import Path
            with (Path(settings.MEDIA_ROOT)/Path(entry.image).name).open('rb') as photo:
                im=Image.open(photo);im.thumbnail((1600,1600));buf=BytesIO();im.convert('RGB').save(buf,format='JPEG',quality=85)
                image=('image/jpeg',buf.getvalue())
            prompt=entry.note[:2000]
            context=build_context(job.user,'food',day,query=entry.name+' '+entry.note)
        if job.task=='exercise':
            exercise=m.Exercise.objects.get(pk=job.payload['exercise'],user=job.user)
            context={'exercise':{'name':exercise.name,'activity_type':exercise.activity_type,'equipment':exercise.equipment}}
            # Constrain muscle names to the canonical groups the muscle map
            # understands, so AI-filled metadata lights up on the map.
            from core.muscles import MUSCLES
            prompt=('Fill conventional exercise aliases and muscle metadata. Classify the movement as compound or isolation. '
                    'Use only these muscle group names for primary_muscles and secondary_muscles: '+', '.join(MUSCLES)+'.')
        result,provider,model=route(job.task,context,prompt,image,job=job)
        with transaction.atomic():
            # Serialize version allocation and acceptance through the same user row.
            type(job.user).objects.select_for_update().get(pk=job.user_id)
            locked=Job.objects.select_for_update().get(pk=job.pk)
            if locked.status!='running' or locked.attempts!=job.attempts: return
            if job.task=='food':
                entry=m.FoodEntry.objects.select_for_update().get(pk=job.payload['entry'],user=job.user)
                if food_snapshot(entry)!=job.payload['snapshot']: raise ProviderError('food_changed_review_required',False)
                for field in ('calories','protein','carbs','fat','fiber','sugar','sodium'): setattr(entry,field,result[field])
                entry.name=', '.join(f['name'] for f in result['foods'])[:160]
                entry.quantity='; '.join(f['amount'] for f in result['foods'])[:120]
                entry.uncertainty=f"{result['confidence']} confidence; {result['calories_low']}-{result['calories_high']} kcal. {result['uncertainty']}"
                entry.state='ai_estimated';entry.full_clean();entry.save()
            if job.task=='exercise':
                exercise=m.Exercise.objects.select_for_update().get(pk=job.payload['exercise'],user=job.user)
                if exercise_snapshot(exercise)!=job.payload['snapshot']: raise ProviderError('exercise_changed_review_required',False)
                for field in ('aliases','primary_muscles','secondary_muscles','classification'):
                    if not getattr(exercise,field): setattr(exercise,field,result[field])
                exercise.full_clean();exercise.save()
            version=(Analysis.objects.filter(user=job.user,task=job.task,local_date=day).aggregate(v=Max('version'))['v'] or 0)+1
            Analysis.objects.create(user=job.user,job=job,task=job.task,local_date=day,version=version,content=result)
            for change in result.get('suggestions',[]):
                if change['kind']=='workout' and context.get('plan',{}).get('truncated'):
                    raise ValidationError('Cannot suggest a change from a truncated plan.')
                validate_change(job.user,change)
                Suggestion.objects.create(user=job.user,job=job,**change)
            locked.result=result;locked.provider=provider;locked.model=model;locked.status='done';locked.error='';locked.lease_until=None;locked.save()
        if job.task=='daily': notify(job.user,'daily')
        if result.get('suggestions'): notify(job.user,'suggestion')
    except (ProviderError,ValidationError,m.FoodEntry.DoesNotExist,m.Exercise.DoesNotExist,OSError,ValueError) as exc:
        code=exc.code if isinstance(exc,ProviderError) else 'invalid_or_changed_data'
        Job.objects.filter(pk=job.pk,status='running',attempts=job.attempts).update(status='failed',error=code,lease_until=None)
