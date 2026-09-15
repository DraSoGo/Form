import os
from statistics import mean

def evaluate(context):
    minimum=int(os.environ.get('AI_TREND_MIN_SAMPLES','6'))
    weight=float(os.environ.get('AI_WEIGHT_CHANGE_PERCENT','2'))
    fat=float(os.environ.get('AI_BODY_FAT_CHANGE_POINTS','2'))
    triggers=[]
    for source,rows in context.get('body_by_source',{}).items():
        for field,threshold,relative in [('weight',weight,True),('body_fat',fat,False)]:
            data=sorted([(str(r['recorded_at']),float(r[field])) for r in rows if r.get(field) is not None])
            if len(data)<minimum or data[-1][0][:10]==data[0][0][:10]: continue
            from datetime import datetime
            span=(datetime.fromisoformat(data[-1][0])-datetime.fromisoformat(data[0][0])).days
            if span<7: continue
            n=len(data)//2
            old,new=mean(v for _,v in data[:n]),mean(v for _,v in data[-n:])
            change=100*(new-old)/old if relative and old else new-old
            if abs(change)>=threshold: triggers.append(f'{source}: {field} sustained change {change:.1f}')
    sleep=context.get('windows',{}).get('7',{})
    if sleep.get('sleep_samples',0)>=5 and float(sleep.get('sleep_hours_average') or 0)<float(os.environ.get('AI_LOW_SLEEP_HOURS','6')):
        triggers.append('At least five recent sleep entries average below threshold')
    workouts=context.get('workouts',[])
    if len(workouts)>=3:
        # Compare the same exercise across completed working sets, excluding warmups.
        by_exercise={}
        for workout in workouts:
            scores={}
            for s in workout['sets']:
                if s['set_type']!='working': continue
                name=s['exercise__name']; scores[name]=max(scores.get(name,0),float(s['weight'])*(1+float(s['reps'])/30))
            for name,score in scores.items(): by_exercise.setdefault(name,[]).append(score)
        for name,scores in by_exercise.items():
            if len(scores)>=3 and scores[0]<scores[1]*.95 and scores[1]<scores[2]*.95:
                triggers.append(f'{name}: performance decreased across three sessions; review recovery and effort')
    return triggers
