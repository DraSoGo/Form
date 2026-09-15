"""Validate suggested values before storing; core revalidates under lock on Accept."""
import math
from django.core.exceptions import ValidationError
from core.models import Exercise

def validate_change(user,change):
    if change.get('kind') not in ('nutrition','workout'): raise ValidationError('Unknown suggestion kind.')
    if not isinstance(change.get('before'),dict) or not isinstance(change.get('proposed'),dict): raise ValidationError('Invalid suggestion payload.')
    if change['kind']=='nutrition':
        allowed={'calories':10000,'protein':1000,'carbs':2000,'fat':1000,'fiber':200}
        for values in (change['before'],change['proposed']):
            if set(values)!=set(allowed): raise ValidationError('Nutrition proposal needs every target field.')
            for key,maximum in allowed.items():
                value=values[key]
                if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or not 0<=value<=maximum:
                    raise ValidationError('Invalid nutrition proposal.')
        current=change['before']['calories'];proposed=change['proposed']['calories']
        if proposed<1200 or current and proposed<current*.8:
            raise ValidationError('Calorie reduction exceeds coaching safety limits.')
    else:
        values=change['proposed']
        if set(values)!={'name','schedule_type','schedule','exercises'} or not isinstance(values['name'],str) or not 1<=len(values['name'])<=120:
            raise ValidationError('Invalid workout proposal fields.')
        schedule=values['schedule']
        if values['schedule_type']=='fixed':
            if not isinstance(schedule,dict) or any(k not in map(str,range(7)) or not isinstance(v,str) for k,v in schedule.items()):
                raise ValidationError('Invalid fixed schedule.')
        elif values['schedule_type']=='rotation':
            if not isinstance(schedule,list) or not 1<=len(schedule)<=31 or any(not isinstance(v,str) for v in schedule):
                raise ValidationError('Invalid rotation.')
        else: raise ValidationError('Invalid schedule type.')
        exercises=values['exercises']
        if not isinstance(exercises,list) or len(exercises)>100: raise ValidationError('Invalid exercise list.')
        for item in exercises:
            if not isinstance(item,dict): raise ValidationError('Invalid exercise.')
            try: exists=Exercise.objects.filter(pk=item.get('exercise'),user=user).exists()
            except (ValueError,ValidationError): exists=False
            if not exists: raise ValidationError('Unknown exercise.')
            for key,low,high,default in [('sets',1,30,3),('rep_min',1,100,8),('rep_max',1,100,12),('rest',0,3600,90),('order',0,100,1)]:
                value=item.get(key,default)
                if not isinstance(value,int) or isinstance(value,bool) or not low<=value<=high: raise ValidationError('Invalid exercise value.')
            if item.get('rep_min',8)>item.get('rep_max',12): raise ValidationError('Invalid rep range.')
            for key in ('rir','rpe'):
                value=item.get(key)
                if value is not None and (not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=10): raise ValidationError('Invalid effort rating.')
