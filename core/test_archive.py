import copy
import csv
import io
import json
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core import serializers
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from core import models as m
from core.archive import export_archive, export_csv, import_archive, validate_archive
from coaching.models import Job, Analysis, Suggestion
from coaching.services import claim_job, decide


class ArchiveTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('archive-user')
        self.old_time = (timezone.now() - timedelta(days=100)).replace(microsecond=123000)

    def payload(self, *objects):
        for obj in objects:
            obj.created_at = self.old_time
            if isinstance(obj, m.Profile):
                obj.summary_time = m.Profile._meta.get_field('summary_time').to_python(obj.summary_time)
        records = json.loads(serializers.serialize('json', objects))
        for record in records:
            record['fields'].pop('user', None)
        return {'schema_version': 1, 'records': records}

    def exercise(self, **kwargs):
        return m.Exercise(name='Squat', primary_muscles=['Quads'], **kwargs)

    def plan(self, exercise, **kwargs):
        values = dict(version=1, name='Plan', schedule_type='rotation', schedule=['Legs', 'Rest'],
                      exercises=[{'exercise': str(exercise.pk), 'sets': 3}])
        values.update(kwargs)
        return m.WorkoutPlan(**values)

    def test_malformed_schema_and_records_rejected(self):
        for version in (True, False, 1.0, '1', None, 0, 3, [], {}):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                validate_archive({'schema_version': version, 'records': []}, self.user)
        for record in ({'model': [], 'pk': 'bad', 'fields': {}}, {'model': 'core.exercise', 'pk': None, 'fields': {}}):
            with self.subTest(record=record), self.assertRaises(ValidationError):
                validate_archive({'schema_version': 1, 'records': [record]}, self.user)

    def test_old_target_archive_without_sugar_sodium_imports(self):
        # Archives exported before the sugar/sodium target fields existed
        # must still validate; the importer fills them as unset.
        target = m.NutritionTarget(version=1, calories=2200, protein=150, carbs=240,
                                   fat=70, fiber=30, reason='old export')
        payload = self.payload(target)
        for record in payload['records']:
            record['fields'].pop('sugar', None)
            record['fields'].pop('sodium', None)
        objects = validate_archive(payload, self.user)
        self.assertEqual(len(objects), 1)
        # New exports carry the fields and validate unchanged.
        self.assertEqual(len(validate_archive(self.payload(target), self.user)), 1)

    def test_plan_semantics_and_refs_validated_at_preview(self):
        exercise = self.exercise()
        for overrides in ({'schedule': 'Legs'}, {'schedule': []}, {'schedule_type': 'fixed', 'schedule': {'8': 'Legs'}},
                          {'exercises': [{'exercise': str(exercise.pk), 'sets': True}]},
                          {'exercises': [{'exercise': str(exercise.pk), 'sets': 100000}]},
                          {'exercises': [{'exercise': str(exercise.pk), 'rir': float('nan')}]},
                          {'exercises': [{'exercise': str(exercise.pk), 'rep_min': 15, 'rep_max': 10}]},
                          {'exercises': [{'exercise': str(exercise.pk), 'notes': {}}]},
                          {'exercises': [{'exercise': 'bad'}]}):
            with self.subTest(overrides=overrides), self.assertRaises(ValidationError):
                validate_archive(self.payload(exercise, self.plan(exercise, **overrides)), self.user)
        with self.assertRaises(ValidationError):
            validate_archive(self.payload(self.plan(exercise)), self.user)
        self.assertEqual(len(validate_archive(self.payload(exercise, self.plan(exercise)), self.user)), 2)

    def test_muscles_and_meal_payloads_are_safe_to_consume(self):
        for value in ('Quads', [{}], [1], ['']):
            exercise = self.exercise()
            exercise.primary_muscles = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_archive(self.payload(exercise), self.user)
        for item in ({'name': 'Food', 'user_id': 1}, {'name': 'Food', 'calories': '-1'}, {'name': 'Food', 'calories': {}}, 'Food'):
            with self.subTest(item=item), self.assertRaises(ValidationError):
                validate_archive(self.payload(m.MealTemplate(name='Meal', items=[item])), self.user)
        meal = m.MealTemplate(name='Meal', items=[{'name': 'Food', 'calories': '0.00', 'sugar': None}])
        self.assertEqual(len(validate_archive(self.payload(meal), self.user)), 1)

    def test_all_unique_collisions_rejected_in_preview(self):
        factories = [lambda: m.Equipment(name='Rack'), lambda: self.exercise(),
                     lambda: m.NutritionTarget(version=1),
                     lambda: Job(task='chat', dedupe='same')]
        for factory in factories:
            with self.subTest(model=type(factory()).__name__):
                with self.assertRaises(ValidationError):
                    validate_archive(self.payload(factory(), factory()), self.user)
                existing = factory()
                existing.user = self.user
                existing.save()
                with self.assertRaises(ValidationError):
                    validate_archive(self.payload(factory()), self.user)
                existing.delete()
        exercise = self.exercise()
        with self.assertRaises(ValidationError):
            validate_archive(self.payload(exercise, self.plan(exercise), self.plan(exercise)), self.user)
        job = Job(task='chat', dedupe='history')
        a = Analysis(job=job, task='chat', local_date=self.old_time.date(), content={'summary': 'Good'})
        b = Analysis(job=job, task='chat', local_date=self.old_time.date(), version=2, content={'summary': 'Good'})
        with self.assertRaises(ValidationError):
            validate_archive(self.payload(job, a, b), self.user)
        other_job = Job(task='chat', dedupe='history-2')
        b.job = other_job
        b.version = 1
        with self.assertRaises(ValidationError):
            validate_archive(self.payload(job, other_job, a, b), self.user)

    def test_profile_retained_only_with_explicit_opt_in(self):
        current = m.Profile.objects.create(user=self.user, goal='gain')
        incoming = m.Profile(goal='lose')
        body = m.BodyMeasurement(weight=70)
        payload = self.payload(incoming, body)
        with self.assertRaises(ValidationError):
            validate_archive(payload, self.user)
        self.assertEqual(len(validate_archive(payload, self.user, keep_profile=True)), 1)
        self.assertEqual(import_archive(payload, self.user, keep_profile=True), 1)
        current.refresh_from_db()
        self.assertEqual(current.goal, 'gain')
        self.assertEqual(m.Profile.objects.count(), 1)
        with self.assertRaises(ValidationError):
            validate_archive(self.payload(incoming, m.Profile()), self.user, keep_profile=True)
        incoming.timezone = 'not-a-timezone'
        with self.assertRaises(ValidationError):
            validate_archive(self.payload(incoming), self.user, keep_profile=True)

    def test_references_are_archive_only_and_import_order_preserves_history(self):
        exercise = self.exercise()
        plan = self.plan(exercise)
        session = m.WorkoutSession(name='Legs', plan=plan)
        workout_set = m.WorkoutSet(session=session, exercise=exercise, completed=False, reps=0)
        payload = self.payload(workout_set, session, plan, exercise)
        self.assertEqual(import_archive(payload, self.user), 4)
        for obj in (workout_set, session, plan, exercise):
            obj.refresh_from_db()
            self.assertEqual(obj.created_at, self.old_time)
        with self.assertRaises(ValidationError):
            validate_archive(self.payload(m.WorkoutSession(name='Legs', plan=plan)), self.user)
        with self.assertRaises(ValidationError):
            validate_archive(payload, self.user)

    def test_imported_coaching_is_validated_and_inert(self):
        job = Job(task='daily', dedupe='old-daily', status='running', lease_until=timezone.now())
        analysis = Analysis(job=job, task='daily', local_date=self.old_time.date(), content={'summary': 'Rest well'})
        values = dict(calories=2000, protein=100, carbs=250, fat=60, fiber=30)
        suggestion = Suggestion(job=job, kind='nutrition', expected_version=1, before=values,
                                proposed=values, reason='Maintain', evidence='Stable trend')
        payload = self.payload(suggestion, analysis, job)
        self.assertEqual(import_archive(payload, self.user), 3)
        job.refresh_from_db()
        suggestion.refresh_from_db()
        self.assertEqual(job.status, 'archived')
        self.assertIsNone(job.lease_until)
        self.assertEqual(suggestion.decision, 'archived')
        self.assertIsNone(claim_job())
        with self.assertRaises(ValidationError):
            decide(self.user, suggestion.pk, True)
        self.assertFalse(m.NutritionTarget.objects.exists())
        self.assertEqual(suggestion.created_at, self.old_time)

    def test_invalid_coaching_shapes_and_relations_rejected(self):
        job = Job(task='chat', dedupe='chat')
        analysis = Analysis(job=job, task='chat', local_date=self.old_time.date(), content={'summary': 'Hi'})
        payload = self.payload(job, analysis)
        for index, field, value in ((0, 'payload', []), (0, 'payload', {'entry': 'bad'}),
                                    (1, 'content', []), (1, 'content', {'summary': {}}), (1, 'task', 'food')):
            broken = copy.deepcopy(payload)
            broken['records'][index]['fields'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                validate_archive(broken, self.user)
        with self.assertRaises(ValidationError):
            validate_archive(self.payload(analysis), self.user)

    def test_null_required_values_rejected_before_insert(self):
        exercise = self.exercise()
        session = m.WorkoutSession(name='Workout')
        workout_set = m.WorkoutSet(session=session, exercise=exercise)
        payload = self.payload(exercise, session, workout_set)
        payload['records'][2]['fields']['session'] = None
        with self.assertRaises(ValidationError):
            validate_archive(payload, self.user)
        payload = self.payload(m.BodyMeasurement(weight=70))
        payload['records'][0]['fields']['created_at'] = None
        with self.assertRaises(ValidationError):
            validate_archive(payload, self.user)

    def test_csv_retains_zero_false_and_blocks_formula_text(self):
        exercise = m.Exercise.objects.create(user=self.user, name='Squat', primary_muscles=['Quads'])
        session = m.WorkoutSession.objects.create(user=self.user, name='Legs')
        m.WorkoutSet.objects.create(session=session, exercise=exercise, reps=0, rest_seconds=0, notes='=1+1')
        row = next(csv.DictReader(io.StringIO(export_csv(self.user, 'workout'))))
        self.assertEqual(row['reps'], '0')
        self.assertEqual(row['rest_seconds'], '0')
        self.assertEqual(row['completed'], 'False')
        self.assertEqual(row['failure'], 'False')
        self.assertEqual(row['notes'], "'=1+1")

    def test_export_excludes_images_and_archive_round_trips(self):
        m.Profile.objects.create(user=self.user)
        m.FoodEntry.objects.create(user=self.user, name='Rice', image='private.jpg', image_status='stored')
        Job.objects.create(user=self.user, task='chat', dedupe='roundtrip')
        payload = export_archive(self.user)
        self.assertEqual(payload['schema_version'], 2)
        self.assertNotIn('private.jpg', json.dumps(payload))
        self.user.delete()
        destination = get_user_model().objects.create_user('destination')
        self.assertEqual(import_archive(payload, destination), 3)
        self.assertEqual(m.FoodEntry.objects.get().image_status, 'not_in_archive')

    def test_v1_exercise_import_supplies_new_safe_defaults(self):
        exercise = self.exercise()
        payload = self.payload(exercise)
        fields = payload['records'][0]['fields']
        fields.pop('activity_type')
        fields.pop('archived')
        fields.pop('default_minutes')
        self.assertEqual(import_archive(payload, self.user), 1)
        exercise.refresh_from_db()
        self.assertEqual(exercise.activity_type, 'strength')
        self.assertFalse(exercise.archived)

    def test_v2_steps_cardio_and_typed_exercise_round_trip(self):
        exercise=m.Exercise.objects.create(user=self.user,name='Bike',activity_type='cardio',default_minutes=35)
        step=m.StepEntry.objects.create(user=self.user,steps=9000)
        session=m.WorkoutSession.objects.create(user=self.user,name='Cardio')
        cardio=m.WorkoutCardio.objects.create(session=session,exercise=exercise,minutes=35)
        payload=export_archive(self.user)
        cardio.delete();session.delete();step.delete();exercise.delete()
        self.user.delete()
        destination=get_user_model().objects.create_user('v2-destination')
        self.assertEqual(import_archive(payload,destination),4)
        self.assertEqual(m.StepEntry.objects.get().steps,9000)
        self.assertEqual(m.WorkoutCardio.objects.get().minutes,35)
        self.assertEqual(m.Exercise.objects.get().activity_type,'cardio')
        self.assertEqual(m.Exercise.objects.get().default_minutes,35)
