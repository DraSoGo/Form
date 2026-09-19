import json
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from django import forms
from .models import *
class StyledModelForm(forms.ModelForm):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        for f in self.fields.values():
            if isinstance(f,forms.DateTimeField):f.widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M',attrs={'type':'datetime-local'})
            elif isinstance(f,forms.DateField):f.widget=forms.DateInput(attrs={'type':'date'})
            elif isinstance(f,forms.TimeField):f.widget=forms.TimeInput(attrs={'type':'time'})
            elif isinstance(f,forms.DecimalField):f.widget.attrs.update({'step':'0.01','inputmode':'decimal'})
def model_form(model,fields=None):
    class F(StyledModelForm):
        class Meta:
            pass
    F.Meta.model=model;F.Meta.fields=fields or '__all__';F.Meta.exclude=['user','id','created_at']
    return forms.modelform_factory(model,form=F,fields=fields,exclude=['user','id','created_at'])


class BodyForm(StyledModelForm):
    """Base measurement form: recorded time, source, weight, body fat."""

    class Meta:
        model = BodyMeasurement
        fields = ["recorded_at", "source", "weight", "body_fat"]


class AdvancedBodyForm(BodyForm):
    """Full form including advanced measurements, used inside a collapsed
    'Advanced measurements' section."""

    class Meta(BodyForm.Meta):
        fields = BodyForm.Meta.fields + [
            "muscle", "visceral_fat", "body_age", "bmr", "bmi"
        ]


SleepForm=model_form(SleepEntry)
CardioForm=model_form(CardioEntry)
StepForm=model_form(StepEntry)
EquipmentForm=model_form(Equipment)
TargetForm=model_form(NutritionTarget,NUTRIENT_FIELDS if False else ['calories','protein','carbs','fat','fiber'])
FoodForm=model_form(FoodEntry,['recorded_at','name','quantity','calories','protein','carbs','fat','fiber','sugar','sodium','note','state'])
LibraryForm=model_form(FoodLibrary)
ExerciseForm=model_form(Exercise)
SetForm=model_form(WorkoutSet,['exercise','order','weight','reps','rir','rpe','set_type','completed','rest_seconds','failure','superset','notes'])
CardioLogForm=model_form(WorkoutCardio,['exercise','order','minutes','completed','notes'])
class ProfileForm(StyledModelForm):
    class Meta:model=Profile;exclude=['id','created_at','user']
    def clean_timezone(self):
        value=self.cleaned_data['timezone']
        try:ZoneInfo(value)
        except (ZoneInfoNotFoundError,ValueError):raise forms.ValidationError('Enter an IANA timezone, e.g. Asia/Bangkok')
        return value
class PlanForm(forms.Form):
    name=forms.CharField(max_length=120)
    schedule_type=forms.ChoiceField(choices=WorkoutPlan._meta.get_field('schedule_type').choices)
    schedule=forms.JSONField(widget=forms.HiddenInput)
    exercises=forms.JSONField(required=False, widget=forms.HiddenInput)

    def clean_exercises(self):
        return self.cleaned_data.get('exercises') or []

    @property
    def editor_data(self):
        data = dict(self.initial)
        if self.is_bound:
            data['schedule_type'] = self.data.get('schedule_type', 'fixed')
            for key in ('schedule', 'exercises'):
                try:
                    data[key] = json.loads(self.data.get(key, 'null'))
                except (TypeError, ValueError):
                    data[key] = None
        return data

class CommaListField(forms.CharField):
    def prepare_value(self, value):
        return ', '.join(value) if isinstance(value, list) else value

    def to_python(self, value):
        return [item.strip() for item in super().to_python(value).split(',') if item.strip()]

class ExerciseForm(StyledModelForm):
    aliases = CommaListField(required=False, help_text='Separate alternate names with commas.')
    primary_muscles = CommaListField(required=False, help_text='Optional. AI can fill this after saving.')
    secondary_muscles = CommaListField(required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [('', 'No equipment')]
        if user is not None:
            choices += [(name, name) for name in Equipment.objects.filter(user=user).values_list('name', flat=True)]
        current = self.instance.equipment if self.instance and self.instance.pk else ''
        if current and current not in dict(choices):
            choices.append((current, current + ' (not in Settings)'))
        self.fields['equipment'] = forms.ChoiceField(choices=choices, required=False)

    def clean(self):
        data = super().clean()
        if data.get('activity_type') == 'cardio':
            if data.get('default_minutes') is None:
                self.add_error('default_minutes', 'Enter the cardio duration in minutes.')
        else:
            data['default_minutes'] = None
        return data

    class Meta:
        model = Exercise
        exclude = ['id', 'created_at', 'user', 'archived']

class FoodForm(FoodForm):
    name = forms.CharField(max_length=160, required=False, label='Food name (optional for photos)')

    def __init__(self, *args, has_photo=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_photo = has_photo or bool(self.instance.image)
        # All nutrient controls remain optional in the browser so selecting a photo
        # never requires fabricated nutrition values. Manual entries validate below.
        for name in ('calories', 'protein', 'carbs', 'fat', 'fiber'):
            self.fields[name].required = False
        self.fields['note'].label = 'Note (optional)'
        self.fields['note'].widget.attrs['placeholder'] = 'Anything useful: ingredients, portion size, sauces…'
        self.fields['quantity'].label = 'Portion / quantity'
        for name in ('protein', 'carbs', 'fat', 'fiber', 'sugar'):
            self.fields[name].label = name.title() + ' (g)'
        self.fields['sodium'].label = 'Sodium (mg)'
        self.fields['calories'].label = 'Energy (kcal)'

    def clean(self):
        data = super().clean()
        if not data.get('name'):
            if self.has_photo:
                data['name'] = 'Photo awaiting analysis'
            else:
                self.add_error('name', 'Enter a food name or attach a photo.')
        for name in ('calories', 'protein', 'carbs', 'fat', 'fiber'):
            if data.get(name) is None and name not in self.errors:
                if self.has_photo:
                    data[name] = 0
                else:
                    self.add_error(name, 'Enter a value, or attach a photo to estimate it.')
        return data
