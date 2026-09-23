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
from core.nutrition_calc import compute_meal, validate_meal
from core.nutrition_ref import table_for_prompt
from .context import build_context,local_now
from .models import Job,Analysis,Suggestion
from .providers import ProviderError
from .router import route
from .schemas import NutritionEstimateV3
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

def enqueue_food(user,entry,reestimate=False):
    if not entry.image and not reestimate: raise ValidationError('This entry has no retained photograph.')
    payload={'entry':str(entry.pk),'snapshot':food_snapshot(entry)}
    if reestimate:
        # User-confirmed components ride along: the AI must keep them fixed
        # and only estimate the remaining unmatched parts.
        payload['reestimate']={
            'confirmed':[
                {'name_th':i.get('name_th',''),'ref_key':i.get('ref_key'),
                 'weight_g':i.get('weight_g'),'user_confirmed':bool(i.get('user_confirmed'))}
                for i in (entry.ai_breakdown or {}).get('items',[])
            ],
            'unmatched':(entry.ai_breakdown or {}).get('unmatched',[]),
        }
    return enqueue(user,'food',payload)

def exercise_snapshot(exercise):
    fields=('name','activity_type','equipment','aliases','primary_muscles','secondary_muscles','classification')
    return hashlib.sha256(json.dumps({k:getattr(exercise,k) for k in fields},sort_keys=True).encode()).hexdigest()

def enqueue_exercise(user,exercise):
    if exercise.user_id!=user.pk: raise ValidationError('Unknown exercise.')
    if exercise.aliases and exercise.primary_muscles and exercise.classification:
        return None
    return enqueue(user,'exercise',{'exercise':str(exercise.pk),'snapshot':exercise_snapshot(exercise)},f'exercise:{exercise.pk}:{exercise_snapshot(exercise)}')


def _food_prompt(note):
    instructions = (
        "You are estimating nutrition from a photo and/or user note. "
        "First identify the whole dish (dish_name_th, cuisine). Then choose ONE strategy:\n"
        "- whole_dish: a suitable [dish] reference exists for the whole meal → 1-2 items using dish refs, weight = estimated total dish weight.\n"
        "- components: clearly separate components (rice + protein + sauce) → one item each.\n"
        "- hybrid: dish baseline + separate items ONLY for additions not in the dish reference (no double-counting oil/sauce/egg/rice already included).\n\n"
        "Portion hierarchy: user-confirmed grams > visual estimate > typical serving. "
        "Support fraction_consumed (e.g. 'กินครึ่งหนึ่ง' → 0.5).\n\n"
        "CRITICAL: if you can see or reasonably infer a MAJOR caloric component (noodles, rice, bread, meat, egg, sauce, broth) that has no suitable reference key, "
        "list it in unmatched[] with estimated_share='major' — NEVER silently omit it and NEVER substitute an unrelated reference (e.g. don't use curry for cake). "
        "Minor garnishes → unmatched with 'minor' is fine.\n\n"
        "Choose ref_key ONLY from this table:\n"
        + table_for_prompt()
        + "\n\n"
        "Estimate EDIBLE portion grams (exclude bones, container, packaging; fried entries already include skin/batter/oil — do NOT add cooking_oil for them; add cooking_oil only for plainly-oily stir-fries not covered by a prepared entry). "
        "If the user note gives an unambiguous cooked weight (e.g. 'ข้าวสุก 150 กรัม'), set user_confirmed=true and weight=that value. "
        "Ambiguous weights ('ไก่ประมาณ 300 กรัม' may be bone-in/whole) → wide min/max, user_confirmed=false, mention in uncertainty_factors_thai."
    )
    return instructions + "\n\nUser note:\n" + note


def _resolve_estimate(result):
    """Convert a V3 route result into computed meal data and validation flags."""
    estimate = NutritionEstimateV3.model_validate(result)
    from core.nutrition_ref import REFERENCE
    # The AI sometimes invents plausible ref_keys absent from the curated
    # table (e.g. cooked_noodles vs egg_noodles). Dropping the whole
    # response over one key wasted every other correct item; instead the
    # item becomes unmatched and the user fixes it in the breakdown UI.
    kept, demoted = [], []
    for item in estimate.items:
        if item.ref_key in REFERENCE:
            kept.append(item)
        else:
            demoted.append(item)
    items = [
        {
            "ref_key": item.ref_key,
            "name_th": item.name_th,
            "weight_g": item.weight_g,
            "min_g": item.min_g,
            "max_g": item.max_g,
            "fraction_consumed": item.fraction_consumed,
            "user_confirmed": item.user_confirmed,
        }
        for item in kept
    ]
    unmatched = [
        {"name_th": u.name_th, "estimated_share": u.estimated_share, "note": u.note}
        for u in estimate.unmatched
    ]
    for item in demoted:
        unmatched.append({
            "name_th": item.name_th or item.ref_key,
            "estimated_share": "major" if item.weight_g >= 40 else "minor",
            "note": f"ไม่มีในตารางอ้างอิง (ref_key: {item.ref_key}) — เพิ่มเป็นส่วนประกอบเองได้",
        })
    # All ref_keys unknown → items may be empty; the meal is still valid,
    # just fully unmatched (INCOMPLETE) so the user can fix it in the UI.
    # (Raising here used to kill note-only analyses of dishes absent from
    # the reference table — e.g. ข้าวผัดกุ้ง — before the correction loop
    # or the user ever saw a result.)
    computed = compute_meal(
        items,
        dish_name=estimate.dish_name_th,
        strategy=estimate.strategy,
        unmatched=unmatched,
        completeness=estimate.completeness,
    )
    flags = validate_meal(computed)
    return estimate, computed, flags

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
            reestimate=job.payload.get('reestimate')
            if not entry.image and not reestimate: raise ProviderError('image_expired',False)
            if entry.image:
                from PIL import Image
                from io import BytesIO
                from django.conf import settings
                from pathlib import Path
                with (Path(settings.MEDIA_ROOT)/Path(entry.image).name).open('rb') as photo:
                    im=Image.open(photo);im.thumbnail((1600,1600));buf=BytesIO();im.convert('RGB').save(buf,format='JPEG',quality=85)
                    image=('image/jpeg',buf.getvalue())
            if reestimate:
                confirmed=reestimate.get('confirmed') or []
                lines=[f"- {c['name_th'] or c.get('ref_key')}: {c.get('weight_g')}g" for c in confirmed if c.get('weight_g')]
                prompt=(
                    _food_prompt(entry.note[:2000])
                    + "\n\nThe user has CONFIRMED these components at these exact weights — keep each one with user_confirmed=true and its exact weight:\n"
                    + ("\n".join(lines) or "(none yet)")
                    + "\nEstimate ONLY the remaining components. Never change confirmed weights. If a confirmed component has no reference key, keep it in items with ref_key 'custom' and leave nutrient values unset."
                )
            else:
                prompt=_food_prompt(entry.note[:2000])
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

        # Food jobs: resolve ingredients, compute deterministically, and retry once on validation issues.
        # Incompleteness (major unmatched components) is NOT a hard failure:
        # the result is saved flagged INCOMPLETE so the user can fix it in the UI.
        food_estimate = food_computed = validation_flags = None
        if job.task == 'food':
            food_estimate, food_computed, validation_flags = _resolve_estimate(result)
            if validation_flags:
                correction_prompt = _food_prompt(entry.note[:2000]) + "\n\nCorrection needed:\n" + "\n".join(validation_flags)
                result, provider, model = route('food', context, correction_prompt, image, job=job)
                food_estimate, food_computed, validation_flags = _resolve_estimate(result)
                if validation_flags:
                    raise ProviderError('food_review_needed', False)

        with transaction.atomic():
            # Serialize version allocation and acceptance through the same user row.
            type(job.user).objects.select_for_update().get(pk=job.user_id)
            locked=Job.objects.select_for_update().get(pk=job.pk)
            if locked.status!='running' or locked.attempts!=job.attempts: return
            if job.task=='food':
                entry=m.FoodEntry.objects.select_for_update().get(pk=job.payload['entry'],user=job.user)
                if food_snapshot(entry)!=job.payload['snapshot']: raise ProviderError('food_changed_review_required',False)

                totals = food_computed['totals']
                range_kcal = food_computed['range_kcal']
                unknown_fields = food_computed['unknown_fields']
                complete = food_computed['complete']

                # Only overwrite entry nutrient fields when the user has not manually corrected/confirmed them.
                # Re-estimate jobs are an explicit user request for fresh
                # numbers, so they overwrite even confirmed/corrected
                # entries; plain analyses still respect manual corrections.
                if entry.state in ('manual', 'ai_estimated') or reestimate:
                    from decimal import Decimal
                    for src, dst in [('kcal','calories'),('protein','protein'),('carbs','carbs'),('fat','fat'),('fiber','fiber'),('sugar','sugar'),('sodium','sodium')]:
                        value = totals.get(src)
                        if value is None:
                            # Fully unmatched meal: keep the previous value
                            # instead of writing NULL into NOT NULL columns
                            # (full_clean used to reject the whole save).
                            continue
                        setattr(entry, dst, Decimal(str(round(float(value), 2))))
                    entry.name = food_estimate.dish_name_th[:160]
                    item_desc = '; '.join(
                        f"{item.name_th or item.ref_key} {item.weight_g:.0f}g"
                        for item in food_estimate.items
                    )[:120]
                    entry.quantity = item_desc
                    entry.state = 'ai_estimated'

                uncertainty_prefix = "INCOMPLETE — " if not complete else ""
                entry.uncertainty = (
                    f"{uncertainty_prefix}{food_estimate.confidence} confidence; "
                    f"{range_kcal[0]:.0f}-{range_kcal[1]:.0f} kcal (ingredient-based). "
                    + '; '.join(food_estimate.uncertainty_factors_thai)
                ).strip()

                entry.ai_breakdown = {
                    "schema": 2,
                    "dish_name": food_estimate.dish_name_th,
                    "cuisine": food_estimate.cuisine,
                    "strategy": food_estimate.strategy,
                    "items": food_computed['ingredients'],
                    "unmatched": food_computed['unmatched'],
                    "totals": totals,
                    "range_kcal": range_kcal,
                    "unknown_fields": unknown_fields,
                    "confidence": food_estimate.confidence,
                    "completeness": food_estimate.completeness if complete else "incomplete",
                    "uncertainty_factors_thai": food_estimate.uncertainty_factors_thai,
                    "validation_flags": validation_flags,
                }
                entry.full_clean();entry.save()
            elif job.task=='exercise':
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
