"""Versioned, insert-only archives. Preview and commit share the same validation."""
import csv
import io
import json
import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.apps import apps
from django.core import serializers
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import JSONField
from . import models

CORE_MODELS = [models.Profile, models.BodyMeasurement, models.SleepEntry, models.CardioEntry,
    models.Equipment, models.NutritionTarget, models.FoodEntry, models.FoodLibrary,
    models.MealTemplate, models.Exercise, models.WorkoutPlan, models.WorkoutSession, models.WorkoutSet]


def archive_models():
    result = list(CORE_MODELS)
    if apps.is_installed('coaching'):
        result.extend(apps.get_model('coaching', name) for name in ['Job', 'Analysis', 'Suggestion'])
    return result


def export_archive(user):
    records = []
    for model in archive_models():
        lookup = {'session__user': user} if model is models.WorkoutSet else {'user': user}
        items = json.loads(serializers.serialize('json', model.objects.filter(**lookup)))
        for item in items:
            item['fields'].pop('user', None)
            if model is models.FoodEntry:
                item['fields']['image'] = ''
                if item['fields']['image_status'] == 'stored':
                    item['fields']['image_status'] = 'not_in_archive'
            if model._meta.label_lower == 'coaching.job':
                item['fields']['status'] = 'archived'
                item['fields']['lease_until'] = None
        records.extend(items)
    return {'schema_version': 1, 'records': records}


def _reference(label, value, keys):
    try:
        pk = apps.get_model(label)._meta.pk.to_python(value)
    except (ValidationError, TypeError, ValueError):
        raise ValidationError('Invalid related record ID.')
    if (label, str(pk)) not in keys:
        raise ValidationError('Missing related record: ' + label)


def _plan(values, keys):
    schedule = values['schedule']
    if values['schedule_type'] == 'fixed':
        valid = isinstance(schedule, dict) and all(k in map(str, range(7)) and isinstance(v, str) for k, v in schedule.items())
    elif values['schedule_type'] == 'rotation':
        valid = isinstance(schedule, list) and 1 <= len(schedule) <= 31 and all(isinstance(v, str) for v in schedule)
    else:
        valid = False
    if not valid:
        raise ValidationError('Invalid plan schedule.')
    exercises = values['exercises']
    if not isinstance(exercises, list) or len(exercises) > 100:
        raise ValidationError('Invalid plan exercises.')
    for item in exercises:
        if not isinstance(item, dict) or set(item) - {'exercise', 'day', 'sets', 'rep_min', 'rep_max', 'rest', 'order', 'rir', 'rpe', 'notes'}:
            raise ValidationError('Invalid exercise prescription.')
        _reference('core.exercise', item.get('exercise'), keys)
        for key, low, high, default in [('sets', 1, 30, 3), ('rep_min', 1, 100, 8), ('rep_max', 1, 100, 12), ('rest', 0, 3600, 90), ('order', 0, 100, 1)]:
            value = item.get(key, default)
            if type(value) is not int or not low <= value <= high:
                raise ValidationError('Invalid exercise ' + key)
        if item.get('rep_min', 8) > item.get('rep_max', 12):
            raise ValidationError('Invalid exercise rep range.')
        for key in ('rir', 'rpe'):
            value = item.get(key)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 10):
                raise ValidationError('Invalid exercise effort.')
        for key, maximum in [('day', 120), ('notes', 2000)]:
            if key in item and (not isinstance(item[key], str) or len(item[key]) > maximum):
                raise ValidationError('Invalid exercise ' + key)


def _suggestion_values(kind, values, keys):
    if not isinstance(values, dict):
        raise ValidationError('Invalid suggestion values.')
    if kind == 'nutrition':
        maximums = dict(calories=10000, protein=1000, carbs=2000, fat=1000, fiber=200)
        if set(values) != set(maximums):
            raise ValidationError('Invalid nutrition suggestion fields.')
        for key, maximum in maximums.items():
            if type(values[key]) not in (int, float) or not math.isfinite(values[key]) or not 0 <= values[key] <= maximum:
                raise ValidationError('Invalid nutrition suggestion value.')
    elif kind == 'workout':
        if set(values) != {'name', 'schedule_type', 'schedule', 'exercises'} or not isinstance(values['name'], str) or not 1 <= len(values['name']) <= 120:
            raise ValidationError('Invalid workout suggestion fields.')
        _plan(values, keys)
    else:
        raise ValidationError('Unknown suggestion kind.')


def _semantics(obj, keys, objects):
    if isinstance(obj, models.Profile):
        try:
            ZoneInfo(obj.timezone)
        except (ValueError, ZoneInfoNotFoundError):
            raise ValidationError('Invalid profile timezone.')
    elif isinstance(obj, models.WorkoutPlan):
        _plan({'schedule_type': obj.schedule_type, 'schedule': obj.schedule, 'exercises': obj.exercises}, keys)
    elif isinstance(obj, models.Exercise):
        for name in ('aliases', 'primary_muscles', 'secondary_muscles'):
            value = getattr(obj, name)
            if not isinstance(value, list) or len(value) > 100 or any(not isinstance(x, str) or not x.strip() or len(x) > 120 for x in value):
                raise ValidationError('Invalid exercise ' + name)
    elif isinstance(obj, models.MealTemplate):
        allowed = {'name', 'quantity', 'calories', 'protein', 'carbs', 'fat', 'fiber', 'sugar', 'sodium'}
        if not isinstance(obj.items, list) or not 1 <= len(obj.items) <= 1000:
            raise ValidationError('Invalid meal items.')
        for item in obj.items:
            if not isinstance(item, dict) or set(item) - allowed or 'name' not in item:
                raise ValidationError('Invalid meal item fields.')
            food = models.FoodEntry(**item)
            food.clean_fields(exclude=['user'])
    label = obj._meta.label_lower
    if label.startswith('coaching.'):
        from coaching.models import TASKS
        tasks = dict(TASKS)
        if label == 'coaching.job':
            if not isinstance(obj.payload, dict) or not isinstance(obj.result, dict):
                raise ValidationError('Invalid job metadata.')
            if 'entry' in obj.payload:
                _reference('core.foodentry', obj.payload['entry'], keys)
            if obj.result:
                _analysis_content(obj.task, obj.result, keys)
        elif label == 'coaching.analysis':
            if obj.task not in tasks or obj.task != objects[('coaching.job', str(obj.job_id))].task:
                raise ValidationError('Analysis task does not match its job.')
            _analysis_content(obj.task, obj.content, keys)
        elif label == 'coaching.suggestion':
            if obj.decision not in ('pending', 'accepted', 'rejected', 'archived') or obj.expected_version < 1:
                raise ValidationError('Invalid suggestion metadata.')
            _suggestion_values(obj.kind, obj.before, keys)
            _suggestion_values(obj.kind, obj.proposed, keys)
            if obj.decision == 'pending':
                obj.decision = 'archived'


def _analysis_content(task, content, keys):
    from coaching.schemas import SCHEMAS
    from pydantic import ValidationError as SchemaError
    try:
        SCHEMAS[task].model_validate(content)
    except (KeyError, SchemaError, TypeError, ValueError) as exc:
        raise ValidationError('Invalid coaching analysis content.') from exc
    for change in content.get('suggestions', []):
        _suggestion_values(change['kind'], change['before'], keys)
        _suggestion_values(change['kind'], change['proposed'], keys)


def _unique(objects):
    """Check database and batch uniqueness, including one-to-one relations."""
    seen = set()
    for obj in objects:
        groups = [(f.name,) for f in obj._meta.fields if f.unique and not f.primary_key]
        groups += list(obj._meta.unique_together)
        groups += [tuple(c.fields) for c in obj._meta.constraints if getattr(c, 'fields', None)]
        for names in groups:
            values = tuple(getattr(obj, obj._meta.get_field(name).attname) for name in names)
            if any(value is None for value in values):
                continue
            key = (type(obj), names, values)
            lookup = dict(zip(names, values))
            if key in seen or type(obj).objects.filter(**lookup).exists():
                raise ValidationError('Duplicate ' + obj._meta.verbose_name + ' (' + ', '.join(names) + '). Import never overwrites existing data.')
            seen.add(key)


def validate_archive(payload, user, *, keep_profile=False):
    if not isinstance(payload, dict) or set(payload) != {'schema_version', 'records'} or type(payload['schema_version']) is not int or payload['schema_version'] != 1:
        raise ValidationError('Unsupported archive schema; expected schema_version 1 and records.')
    records = payload['records']
    if not isinstance(records, list) or len(records) > 50000:
        raise ValidationError('Archive must contain at most 50,000 records.')
    try:
        json.dumps(payload, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValidationError('Archive contains invalid JSON values.') from exc
    allowed = {m._meta.label_lower: m for m in archive_models()}
    keys = set()
    prepared = []
    skip_profile = keep_profile is True and models.Profile.objects.filter(user=user).exists()
    profiles = 0
    for record in records:
        if not isinstance(record, dict) or set(record) != {'model', 'pk', 'fields'} or not isinstance(record['model'], str):
            raise ValidationError('Malformed record.')
        model = allowed.get(record['model'])
        if model is None or not isinstance(record['fields'], dict):
            raise ValidationError('Unknown model.')
        try:
            if not isinstance(record['pk'], str):
                raise ValidationError('Invalid record ID.')
            pk = model._meta.pk.to_python(record['pk'])
        except (ValueError, ValidationError, TypeError) as exc:
            raise ValidationError('Invalid record ID.') from exc
        key = (record['model'], str(pk))
        skipping = model is models.Profile and skip_profile
        if key in keys or (not skipping and model.objects.filter(pk=pk).exists()):
            raise ValidationError('Duplicate record ID. Import never overwrites existing data.')
        keys.add(key)
        expected = {f.name for f in model._meta.fields} - {'id', 'user'}
        if set(record['fields']) != expected:
            raise ValidationError('Missing or unknown fields for ' + record['model'])
        fields = {**record['fields']}
        if 'user' in {f.name for f in model._meta.fields}:
            fields['user'] = user.pk
        if model is models.Profile:
            profiles += 1
            if profiles > 1:
                raise ValidationError('Archive contains multiple profiles.')
        if model is models.FoodEntry and fields['image']:
            raise ValidationError('Archives cannot reference filesystem images.')
        if model._meta.label_lower == 'coaching.job':
            fields['status'] = 'archived'
            fields['lease_until'] = None
        try:
            obj = list(serializers.deserialize('json', json.dumps([{'model': record['model'], 'pk': str(pk), 'fields': fields}])))[0].object
            # JSON semantics and archive-only FK references are checked below.
            obj.clean_fields(exclude=[f.name for f in model._meta.fields if f.is_relation or isinstance(f, JSONField) or (f.null and getattr(obj, f.attname) is None)])
            obj.clean()
            if obj.created_at is None:
                raise ValidationError('Missing historical creation timestamp.')
        except Exception as exc:
            raise ValidationError('Invalid record fields: ' + str(exc)) from exc
        prepared.append(obj)
    objects = {(obj._meta.label_lower, str(obj.pk)): obj for obj in prepared}
    for obj in prepared:
        for field in obj._meta.fields:
            if not field.is_relation or field.name == 'user':
                continue
            value = getattr(obj, field.attname)
            if value is None and not field.null:
                raise ValidationError('Missing required relation: ' + field.name)
            if value is not None:
                _reference(field.related_model._meta.label_lower, value, keys)
        _semantics(obj, keys, objects)
    if skip_profile:
        prepared = [obj for obj in prepared if not isinstance(obj, models.Profile)]
    _unique(prepared)
    return prepared


@transaction.atomic
def import_archive(payload, user, *, keep_profile=False):
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=user.pk)
    objects = validate_archive(payload, user, keep_profile=keep_profile)
    order = {m: i for i, m in enumerate(archive_models())}
    for obj in sorted(objects, key=lambda o: order[type(o)]):
        created_at = obj.created_at
        obj.save(force_insert=True)
        # auto_now_add replaces input on INSERT; restore the validated historical timestamp.
        type(obj).objects.filter(pk=obj.pk).update(created_at=created_at)
    return len(objects)


def export_csv(user, domain):
    model = {'body': models.BodyMeasurement, 'nutrition': models.FoodEntry, 'workout': models.WorkoutSet}[domain]
    lookup = {'session__user': user} if domain == 'workout' else {'user': user}
    fields = [f for f in model._meta.fields if f.name not in ['user', 'image']]
    stream = io.StringIO()
    writer = csv.writer(stream)
    writer.writerow([f.name for f in fields])
    for obj in model.objects.filter(**lookup):
        row = []
        for field in fields:
            raw = getattr(obj, field.attname)
            value = '' if raw is None else str(raw)
            if value.startswith(('=', '+', '-', '@', '\t', '\r')):
                value = "'" + value
            row.append(value)
        writer.writerow(row)
    return stream.getvalue()
