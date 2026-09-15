"""Bounded aggregates shared by every coaching task; never include photo paths."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from django.db.models import Sum,Avg,Q
from django.utils import timezone
from core import models as m
from core.services import active_target,active_plan,target_payload,plan_payload,weekly_volume

def local_now(user):
    profile=m.Profile.objects.filter(user=user).first() or m.Profile(user=user)
    return timezone.now().astimezone(ZoneInfo(profile.timezone))
def build_context(user,task,date=None,query=""):
    date=date or local_now(user).date()
    profile=m.Profile.objects.filter(user=user).first() or m.Profile(user=user)
    context={'date':str(date),'profile':{k:getattr(profile,k) for k in ('age','sex','height','goal','activity')}}
    target=active_target(user)
    if target: context['target']={'version':target.version,'values':target_payload(target)}
    if task=='food':
        import re
        tokens=re.findall(r'[^\W_]+',query[:1000],re.UNICODE)[:12]
        foods=m.FoodLibrary.objects.filter(user=user)
        if tokens:
            match=Q()
            for token in tokens: match |= Q(name__icontains=token)|Q(quantity__icontains=token)
            relevant=foods.filter(match)
            if relevant.exists(): foods=relevant
        context['confirmed_foods']=list(foods.order_by('-created_at').values('name','quantity','calories','protein','carbs','fat','fiber')[:20])
        return context
    plan=active_plan(user)
    if plan: context['plan']={'version':plan.version,'values':plan_payload(plan)}
    context['exercise_library']=list(m.Exercise.objects.filter(user=user).values('id','name','equipment','primary_muscles')[:150])
    context['equipment']=list(m.Equipment.objects.filter(user=user).values_list('name',flat=True)[:60])
    context['windows']={}
    tz=ZoneInfo(profile.timezone)
    from datetime import datetime,time
    end=datetime.combine(date+timedelta(days=1),time.min,tzinfo=tz)
    for days in (1,7,14,30):
        start=end-timedelta(days=days)
        foods=m.FoodEntry.objects.filter(user=user,recorded_at__gte=start,recorded_at__lt=end)
        totals=foods.aggregate(**{k:Sum(k) for k in ('calories','protein','carbs','fat','fiber')})
        sleeps=m.SleepEntry.objects.filter(user=user,date__gte=start.date(),date__lte=date)
        logged_days=len({r.astimezone(tz).date() for r in foods.values_list('recorded_at',flat=True)})
        context['windows'][str(days)]={'nutrition_totals':totals,'nutrition_daily_average':{k:float(v or 0)/logged_days if logged_days else None for k,v in totals.items()},'food_count':foods.count(),'logged_days':logged_days,'window_days':days,'coverage_note':'Averages use logged days only. Unlogged days have unknown intake, and logged days may be incomplete.','sleep_hours_average':sleeps.aggregate(value=Avg('hours'))['value'],'sleep_samples':sleeps.count()}
    context['body_by_source']={}
    bodies=m.BodyMeasurement.objects.filter(user=user,recorded_at__gte=end-timedelta(days=30),recorded_at__lt=end).order_by('-recorded_at')[:120]
    for row in bodies:
        context['body_by_source'].setdefault(row.source,[]).append({k:getattr(row,k) for k in ('recorded_at','weight','body_fat','muscle','bmr','bmi')})
    sessions=m.WorkoutSession.objects.filter(user=user,started_at__gte=end-timedelta(days=30),started_at__lt=end).order_by('-started_at')[:12]
    context['workouts']=[]
    for session in sessions:
        sets=list(m.WorkoutSet.objects.filter(session=session,completed=True).values('exercise__name','weight','reps','rir','rpe','set_type','failure')[:60])
        context['workouts'].append({'name':session.name,'started_at':session.started_at,'sets':sets})
    context['weekly_volume']=weekly_volume(user)
    context['cardio']=list(m.CardioEntry.objects.filter(user=user,recorded_at__gte=end-timedelta(days=7),recorded_at__lt=end).values('kind','minutes')[:30])
    # Limit even unusually large plans before serializing to an upstream provider.
    if 'plan' in context:
        import json
        if len(json.dumps(context['plan'],default=str))>16000:
            context['plan']={'version':plan.version,'name':plan.name,'truncated':True,'instruction':'Plan exceeds context budget. Do not propose workout plan changes; ask user to review a smaller plan.'}
    # Every row count is bounded; cap aggregate payload independently as well.
    import json
    while len(json.dumps(context,default=str))>48000 and context['workouts']:
        context['workouts'].pop()
    if len(json.dumps(context,default=str))>48000:
        for source in context['body_by_source']: context['body_by_source'][source]=context['body_by_source'][source][:20]
    while len(json.dumps(context,default=str))>48000 and context['exercise_library']:
        context['exercise_library'].pop()
    return context
