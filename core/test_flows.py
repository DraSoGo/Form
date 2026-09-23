"""Domain and browser regressions without external services or shared media."""
import io
import tempfile
from datetime import timedelta, datetime, time
from decimal import Decimal
from pathlib import Path

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import (
    BodyMeasurement, Equipment, Exercise, FoodEntry, FoodLibrary, LoginAttempt,
    MealTemplate, NutritionTarget, Profile, SleepEntry, StepEntry, WorkoutCardio,
    WorkoutPlan, WorkoutSession, WorkoutSet,
)
from .forms import ExerciseForm, StepForm
from .services import (
    active_plan, active_target, calculate_target, create_plan, create_target,
    delete_image, nutrition_totals, retain_images, save_image, start_session, weekly_volume,
)


@override_settings(
    SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
    ALLOWED_HOSTS=['testserver'],
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class CoreFlowTests(TestCase):
    password = 'test-owner-long-password'

    def setUp(self):
        self.user = get_user_model().objects.create_user('owner', password=self.password)
        self.client.force_login(self.user)
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.media.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.exercise = Exercise.objects.create(
            user=self.user, name='Bench press', primary_muscles=['Chest'], secondary_muscles=['Triceps'],
        )

    def plan_data(self, **changes):
        data = dict(name='Training', schedule_type='rotation', schedule=['Push', 'Rest'],
                    exercises=[{'exercise': str(self.exercise.pk), 'day': 'Push', 'sets': 2,
                                'rep_min': 6, 'rep_max': 10, 'rest': 120}])
        data.update(changes)
        return data

    def food_data(self, **changes):
        return dict({'recorded_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
                     'name': 'Rice and chicken', 'quantity': '1 bowl', 'calories': '500',
                     'protein': '40', 'carbs': '60', 'fat': '10', 'fiber': '4', 'state': 'manual'}, **changes)

    def image_upload(self, mime='image/png'):
        data = io.BytesIO()
        Image.new('RGB', (10, 10), 'green').save(data, 'PNG')
        return SimpleUploadedFile('meal.png', data.getvalue(), content_type=mime)

    def test_calculation_requires_explicit_profile(self):
        BodyMeasurement.objects.create(user=self.user, weight=80)
        with self.assertRaises(ValidationError):
            calculate_target(self.user)
        self.assertFalse(NutritionTarget.objects.exists())
        self.assertFalse(BodyMeasurement.objects.filter(source='calculated').exists())

    def test_calculation_preserves_scale_source_and_valid_formula(self):
        Profile.objects.create(user=self.user, age=30, sex='male', height=180, activity=Decimal('1.4'))
        scale = BodyMeasurement.objects.create(user=self.user, source='smart_scale', weight=80, bmr=1900)
        target = calculate_target(self.user)
        self.assertEqual(target.calories, 2492)
        self.assertEqual(target.protein, 128)
        calculated = BodyMeasurement.objects.get(source='calculated')
        self.assertEqual(calculated.bmr, 1780)
        self.assertEqual(calculated.bmi, Decimal('24.69'))
        scale.refresh_from_db()
        self.assertEqual(scale.bmr, 1900)
        self.assertEqual(BodyMeasurement.objects.count(), 2)

    def test_target_versions_are_immutable_and_stale_save_rejected(self):
        values = dict(calories=2000, protein=140, carbs=225, fat=60, fiber=30)
        first = create_target(self.user, values, expected_version=0)
        second = create_target(self.user, {**values, 'calories': 2200}, expected_version=1)
        self.assertEqual(active_target(self.user), second)
        first.refresh_from_db()
        self.assertEqual(first.calories, 2000)
        for version in (1, 'invalid'):
            with self.assertRaises(ValidationError):
                create_target(self.user, values, expected_version=version)
        self.assertEqual(NutritionTarget.objects.count(), 2)

    def test_plan_versions_preserve_existing_session_and_reject_stale(self):
        first = create_plan(self.user, self.plan_data(), expected_version=0)
        session = start_session(self.user, first, 'Push')
        changed = {**self.plan_data(), 'name': 'Revised', 'schedule': ['Push', 'Pull', 'Rest']}
        second = create_plan(self.user, changed, expected_version=1)
        self.assertEqual(active_plan(self.user), second)
        session.refresh_from_db()
        first.refresh_from_db()
        self.assertEqual(session.plan_id, first.pk)
        self.assertEqual(first.schedule, ['Push', 'Rest'])
        with self.assertRaises(ValidationError):
            create_plan(self.user, changed, expected_version=1)
        self.assertEqual(WorkoutPlan.objects.count(), 2)

    def test_plan_rejects_invalid_ranges_and_foreign_exercises(self):
        other = get_user_model().objects.create_user('other')
        foreign = Exercise.objects.create(user=other, name='Other exercise', primary_muscles=['Back'])
        for changes in ({'rep_min': 12, 'rep_max': 5}, {'sets': 0}, {'exercise': str(foreign.pk)}):
            data = self.plan_data()
            data['exercises'][0].update(changes)
            with self.assertRaises(ValidationError):
                create_plan(self.user, data)
        self.assertFalse(WorkoutPlan.objects.exists())

    def test_fixed_dashboard_uses_weekday(self):
        data = {**self.plan_data(), 'schedule_type': 'fixed',
                'schedule': {str(timezone.localdate().weekday()): 'Push'}}
        create_plan(self.user, data)
        self.assertEqual(self.client.get('/').context['scheduled'], 'Push')

    def test_rotation_only_advances_when_finished_including_rest(self):
        plan = create_plan(self.user, self.plan_data())
        session = start_session(self.user, plan, 'Push')
        self.assertEqual(self.client.get('/').context['scheduled'], 'Push')
        self.client.post(f'/workouts/session/{session.pk}/', {'action': 'finish', 'notes': 'Done'})
        self.assertEqual(self.client.get('/').context['scheduled'], 'Rest')
        self.client.post('/workouts/start/', {'name': 'Rest'})
        self.assertEqual(self.client.get('/').context['scheduled'], 'Push')

    def test_planned_sets_and_complete_toggle(self):
        plan = create_plan(self.user, self.plan_data())
        session = start_session(self.user, plan, 'Push')
        self.assertEqual(session.sets.count(), 2)
        item = session.sets.first()
        self.assertEqual((item.reps, item.rest_seconds, item.completed), (6, 120, False))
        self.client.post(f'/workouts/set/{item.pk}/complete/')
        item.refresh_from_db()
        self.assertTrue(item.completed)
        self.client.post(f'/workouts/set/{item.pk}/complete/')
        item.refresh_from_db()
        self.assertFalse(item.completed)

    def test_typed_exercise_form_uses_owned_equipment_and_allows_blank_muscles(self):
        Equipment.objects.create(user=self.user, name='Dumbbell')
        other = get_user_model().objects.create_user('equipment-owner')
        Equipment.objects.create(user=other, name='Treadmill')
        form = ExerciseForm(data={'name': 'Walk', 'activity_type': 'cardio', 'default_minutes': '30', 'aliases': '',
            'primary_muscles': '', 'secondary_muscles': '', 'equipment': 'Dumbbell',
            'classification': 'compound'}, user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(list(form.fields['equipment'].choices),
                         [('', 'No equipment'), ('Dumbbell', 'Dumbbell')])
        exercise = form.save(commit=False)
        self.assertEqual((exercise.activity_type, exercise.default_minutes, exercise.primary_muscles),
                         ('cardio', 30, []))
        self.assertFalse(exercise.archived)
        self.assertFalse(ExerciseForm(data={**form.data, 'equipment': 'Treadmill'}, user=self.user).is_valid())

    def test_cardio_exercise_form_requires_duration_and_library_separates_metadata(self):
        data = {'name': 'Walk', 'activity_type': 'cardio', 'aliases': '',
                'primary_muscles': '', 'secondary_muscles': '', 'equipment': '',
                'classification': ''}
        self.assertFalse(ExerciseForm(data=data, user=self.user).is_valid())
        form_page = self.client.get('/add/exercise/')
        self.assertContains(form_page, 'Duration (minutes)')
        self.assertContains(form_page, 'data-exercise-form')
        cardio = Exercise.objects.create(user=self.user, name='Walk', activity_type='cardio',
                                          default_minutes=30)
        library = self.client.get('/workouts/')
        self.assertContains(library, '<span class="exercise-name">Walk</span>', html=True)
        self.assertContains(library, '<small class="exercise-meta">Cardio · 30 min · No equipment</small>', html=True)
        # The cardio default duration surfaces on the day page's add form.
        from .services import create_plan
        create_plan(self.user, self.plan_data())
        self.assertContains(self.client.get('/workouts/day/Push/'), 'data-default-minutes="30"')

    def test_strength_exercise_does_not_keep_cardio_duration(self):
        form = ExerciseForm(data={'name': 'Squat', 'activity_type': 'strength',
            'default_minutes': '45', 'aliases': '', 'primary_muscles': 'Quads',
            'secondary_muscles': '', 'equipment': '', 'classification': 'compound'},
            user=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save(commit=False).default_minutes)

    def test_steps_require_nonnegative_integer(self):
        self.assertTrue(StepForm(data={'date': timezone.localdate(), 'steps': '12345', 'note': ''}).is_valid())
        self.assertFalse(StepForm(data={'date': timezone.localdate(), 'steps': '-1', 'note': ''}).is_valid())

    def test_cardio_plan_creates_duration_log_and_rejects_strength_fields(self):
        cardio = Exercise.objects.create(user=self.user, name='Elliptical', activity_type='cardio')
        data = self.plan_data(exercises=[{'exercise': str(cardio.pk), 'day': 'Push', 'minutes': 25}])
        plan = create_plan(self.user, data)
        session = start_session(self.user, plan, 'Push')
        self.assertEqual(session.sets.count(), 0)
        self.assertEqual((session.cardio.first().exercise, session.cardio.first().minutes), (cardio, 25))
        for bad in (0, 1441, '25'):
            with self.subTest(minutes=bad), self.assertRaises(ValidationError):
                create_plan(self.user, self.plan_data(exercises=[{'exercise': str(cardio.pk), 'day': 'Push', 'minutes': bad}]))
        with self.assertRaises(ValidationError):
            create_plan(self.user, self.plan_data(exercises=[{'exercise': str(cardio.pk), 'day': 'Push', 'minutes': 25, 'sets': 3}]))

    def test_historical_plan_shape_survives_later_exercise_type_edit(self):
        plan=create_plan(self.user,self.plan_data())
        self.exercise.activity_type='cardio';self.exercise.save()
        session=start_session(self.user,plan,'Push')
        self.assertEqual(session.sets.count(),2)
        self.assertEqual(session.cardio.count(),0)

    def test_archived_exercise_cannot_enter_new_plan_but_history_survives(self):
        plan = create_plan(self.user, self.plan_data())
        session = start_session(self.user, plan, 'Push')
        self.assertEqual(self.client.post(f'/exercise/{self.exercise.pk}/archive/').status_code, 302)
        self.exercise.refresh_from_db()
        self.assertTrue(self.exercise.archived)
        self.assertEqual(session.sets.count(), 2)
        with self.assertRaises(ValidationError):
            create_plan(self.user, self.plan_data())
        self.assertNotContains(self.client.get('/workouts/plan/'), 'Bench press')

    def test_plan_allows_duplicate_schedule_day_names(self):
        from .services import create_plan
        data = self.plan_data(schedule_type='fixed',
                              schedule={'0': 'Push', '1': 'Push', '2': 'Push', '3': 'Push',
                                        '4': 'Push', '5': 'Push', '6': 'Push'})
        plan = create_plan(self.user, data)
        self.assertEqual(plan.schedule['0'], 'Push')

    def test_plan_rest_only_schedule_rejects_exercise_days(self):
        from .services import create_plan
        data = self.plan_data(schedule_type='fixed',
                              schedule={'0': 'Rest', '1': 'Rest', '2': 'Rest', '3': 'Rest',
                                        '4': 'Rest', '5': 'Rest', '6': 'Rest'})
        with self.assertRaises(ValidationError):
            create_plan(self.user, data)

    def test_plan_rejects_day_not_in_schedule(self):
        from .services import create_plan
        data = self.plan_data(schedule=['Push', 'Rest'],
                              exercises=[{'exercise': str(self.exercise.pk), 'day': 'Pull',
                                          'sets': 3, 'rep_min': 8, 'rep_max': 12, 'rest': 90}])
        with self.assertRaises(ValidationError):
            create_plan(self.user, data)

    def test_plan_valid_push_pull_legs_full_week(self):
        from .services import create_plan
        row = Exercise.objects.create(user=self.user, name='Row', primary_muscles=['Back'])
        squat = Exercise.objects.create(user=self.user, name='Squat', primary_muscles=['Quads'])
        data = self.plan_data(schedule_type='fixed',
                              schedule={'0': 'Push', '1': 'Pull', '2': 'Legs', '3': 'Rest',
                                        '4': 'Push', '5': 'Pull', '6': 'Legs'},
                              exercises=[
                                  {'exercise': str(self.exercise.pk), 'day': 'Push', 'sets': 3,
                                   'rep_min': 8, 'rep_max': 12, 'rest': 90},
                                  {'exercise': str(row.pk), 'day': 'Pull', 'sets': 4,
                                   'rep_min': 8, 'rep_max': 12, 'rest': 120},
                                  {'exercise': str(squat.pk), 'day': 'Legs', 'sets': 5,
                                   'rep_min': 5, 'rep_max': 8, 'rest': 180},
                              ])
        plan = create_plan(self.user, data)
        self.assertEqual(len(plan.exercises), 3)
        self.assertEqual({e['day'] for e in plan.exercises}, {'Push', 'Pull', 'Legs'})

    def test_steps_replace_body_cardio_and_legacy_cardio_moves_to_training(self):
        from .models import CardioEntry, StepEntry
        legacy = CardioEntry.objects.create(user=self.user, kind='Run', minutes=20)
        step = StepEntry.objects.create(user=self.user, steps=8500)
        body = self.client.get('/body/')
        self.assertContains(body, 'id="steps"')
        self.assertContains(body, '8500')
        self.assertNotContains(body, '+ Cardio')
        training = self.client.get('/workouts/')
        self.assertContains(training, 'Legacy cardio')
        self.assertContains(training, 'Run')
        self.assertEqual(self.client.post(f'/delete/step/{step.pk}/').status_code, 302)
        self.assertFalse(StepEntry.objects.filter(pk=step.pk).exists())
        self.assertTrue(CardioEntry.objects.filter(pk=legacy.pk).exists())

    def test_owned_delete_is_post_only_and_food_delete_removes_photo(self):
        name = save_image(self.image_upload())
        entry = FoodEntry.objects.create(user=self.user, name='Meal', image=name)
        self.assertEqual(self.client.get(f'/delete/food/{entry.pk}/').status_code, 405)
        other = get_user_model().objects.create_user('delete-owner')
        other_entry = FoodEntry.objects.create(user=other, name='Private')
        self.assertEqual(self.client.post(f'/delete/food/{other_entry.pk}/').status_code, 404)
        self.assertEqual(self.client.post(f'/delete/food/{entry.pk}/').status_code, 302)
        self.assertFalse(FoodEntry.objects.filter(pk=entry.pk).exists())
        self.assertFalse((Path(self.media.name) / name).exists())

    def test_session_activity_delete_keeps_session(self):
        cardio_exercise=Exercise.objects.create(user=self.user,name='Bike',activity_type='cardio')
        session=WorkoutSession.objects.create(user=self.user,name='Mixed')
        strength=WorkoutSet.objects.create(session=session,exercise=self.exercise)
        cardio=WorkoutCardio.objects.create(session=session,exercise=cardio_exercise,minutes=20)
        page=self.client.get(f'/workouts/session/{session.pk}/')
        self.assertContains(page,f'/delete/set/{strength.pk}/')
        self.assertContains(page,f'/delete/workout-cardio/{cardio.pk}/')
        self.assertEqual(self.client.post(f'/delete/set/{strength.pk}/').status_code,302)
        self.assertEqual(self.client.post(f'/delete/workout-cardio/{cardio.pk}/').status_code,302)
        self.assertTrue(WorkoutSession.objects.filter(pk=session.pk).exists())
        self.assertFalse(WorkoutSet.objects.filter(pk=strength.pk).exists())
        self.assertFalse(WorkoutCardio.objects.filter(pk=cardio.pk).exists())

    def test_copy_last_preserves_actuals_and_resets_completion(self):
        plan = create_plan(self.user, self.plan_data())
        previous = start_session(self.user, plan, 'Push')
        item = previous.sets.first()
        item.weight, item.reps, item.completed = 70, 9, True
        item.save()
        current = start_session(self.user, plan, 'Push', copy_last=True)
        copied = current.sets.first()
        self.assertNotEqual(copied.pk, item.pk)
        self.assertEqual((copied.weight, copied.reps, copied.completed), (70, 9, False))
        item.refresh_from_db()
        self.assertTrue(item.completed)
        self.assertEqual(previous.sets.count(), 2)

    def test_weekly_volume_counts_completed_work_and_indirect_only(self):
        current = WorkoutSession.objects.create(user=self.user, name='Push')
        old = WorkoutSession.objects.create(user=self.user, name='Old', started_at=timezone.now()-timedelta(days=8))
        for session, completed, kind in [(current, True, 'working'), (current, True, 'drop'),
                                         (current, True, 'warmup'), (current, False, 'working'),
                                         (old, True, 'working')]:
            WorkoutSet.objects.create(session=session, exercise=self.exercise, completed=completed, set_type=kind)
        # weekly_volume now returns the full canonical muscle map (zeros
        # included); assert the exercised muscles and spot-check a zero.
        volume = weekly_volume(self.user)
        self.assertEqual(volume['Chest'], {'direct': 2, 'indirect': 0})
        self.assertEqual(volume['Triceps'], {'direct': 0, 'indirect': 2})
        self.assertEqual(volume['Back'], {'direct': 0, 'indirect': 0})
        self.assertNotIn('Old', [k for k, v in volume.items() if v['direct'] or v['indirect']])

    def test_body_create_and_edit_preserve_other_history(self):
        old = BodyMeasurement.objects.create(user=self.user, weight=83, source='smart_scale')
        payload = {'recorded_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'), 'source': 'manual', 'weight': '81'}
        self.assertEqual(self.client.post('/body/', payload).status_code, 302)
        latest = BodyMeasurement.objects.exclude(pk=old.pk).get()
        self.assertEqual(self.client.post(f'/edit/body/{latest.pk}/', {**payload, 'weight': '80'}).status_code, 302)
        old.refresh_from_db()
        latest.refresh_from_db()
        self.assertEqual((old.weight, latest.weight), (83, 80))
        self.assertEqual(BodyMeasurement.objects.count(), 2)

    def test_manual_food_library_and_reuse(self):
        response = self.client.post('/nutrition/new/', self.food_data(save_library='1'))
        self.assertEqual(response.status_code, 302)
        library = FoodLibrary.objects.get()
        original = FoodEntry.objects.get()
        self.assertEqual(original.state, 'manual')
        self.assertEqual(self.client.post(f'/library/{library.pk}/use/').status_code, 302)
        copied = FoodEntry.objects.exclude(pk=original.pk).get()
        self.assertEqual((copied.calories, copied.protein, copied.state), (500, 40, 'confirmed'))

    def test_food_correction_updates_totals_without_duplicate(self):
        self.client.post('/nutrition/new/', self.food_data())
        entry = FoodEntry.objects.get()
        self.assertEqual(self.client.post(f'/nutrition/{entry.pk}/', self.food_data(calories='650')).status_code, 302)
        entry.refresh_from_db()
        self.assertEqual((entry.calories, entry.state), (650, 'user_corrected'))
        self.assertEqual(FoodEntry.objects.count(), 1)
        now = timezone.now()
        self.assertEqual(nutrition_totals(self.user, now-timedelta(days=1), now+timedelta(days=1))['calories'], 650)

    def test_meal_template_snapshots_food_before_later_correction(self):
        self.client.post('/nutrition/new/', self.food_data())
        entry = FoodEntry.objects.get()
        self.client.post('/templates/save/', {'name': 'Lunch', 'food_ids': [str(entry.pk)]})
        template = MealTemplate.objects.get()
        entry.calories = 900
        entry.save()
        self.assertEqual(self.client.post(f'/templates/{template.pk}/use/').status_code, 302)
        copied = FoodEntry.objects.exclude(pk=entry.pk).get()
        self.assertEqual((copied.calories, copied.state), (500, 'confirmed'))

    def test_image_content_validation_reencodes_valid_image_and_rejects_mismatch(self):
        filename = save_image(self.image_upload())
        with Image.open(Path(self.media.name)/filename) as image:
            self.assertEqual(image.format, 'JPEG')
        for upload in (self.image_upload('image/jpeg'), SimpleUploadedFile('fake.png', b'invalid', content_type='image/png')):
            with self.assertRaises(ValidationError):
                save_image(upload)
        self.assertEqual(len(list(Path(self.media.name).iterdir())), 1)

    def test_photo_only_food_does_not_require_invented_nutrients(self):
        data = self.food_data(name='', calories='', protein='', carbs='', fat='', fiber='')
        response = self.client.post('/nutrition/new/', {**data, 'photo': self.image_upload()})
        self.assertEqual(response.status_code, 302)
        entry = FoodEntry.objects.get()
        self.assertTrue(entry.image)
        self.assertEqual(entry.calories, 0)

    def test_food_photo_picker_does_not_force_mobile_camera(self):
        response = self.client.get('/nutrition/new/')
        self.assertContains(response, 'accept="image/jpeg,image/png,image/webp"')
        self.assertNotContains(response, 'capture=')

    def test_site_brand_uses_logo_for_header_and_browser_icon(self):
        response = self.client.get('/')
        self.assertContains(response, 'class="brand-logo"')
        self.assertContains(response, 'rel="icon"')
        self.assertContains(response, 'rel="apple-touch-icon"')

    def test_delete_photo_preserves_food_and_nutrients(self):
        name = save_image(self.image_upload())
        entry = FoodEntry.objects.create(user=self.user, name='Meal', calories=500, image=name, image_status='stored')
        response = self.client.get(f'/photos/{entry.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'private, no-store')
        self.assertTrue(b''.join(response.streaming_content))
        self.assertEqual(self.client.post(f'/photos/{entry.pk}/delete/').status_code, 302)
        entry.refresh_from_db()
        self.assertEqual((entry.image, entry.image_status, entry.calories), ('', 'deleted', 500))
        self.assertFalse((Path(self.media.name)/name).exists())

    def test_retention_removes_old_image_only(self):
        Profile.objects.create(user=self.user, image_retention_days=30)
        old_name, recent_name = save_image(self.image_upload()), save_image(self.image_upload())
        old = FoodEntry.objects.create(user=self.user, name='Old meal', calories=300, image=old_name,
                                       recorded_at=timezone.now()-timedelta(days=31))
        FoodEntry.objects.create(user=self.user, name='Recent meal', image=recent_name)
        self.assertEqual(retain_images(), 1)
        old.refresh_from_db()
        self.assertEqual((old.image, old.image_status, old.calories), ('', 'expired', 300))
        self.assertTrue((Path(self.media.name)/recent_name).exists())
        self.assertEqual(FoodEntry.objects.count(), 2)

    def test_anonymous_pages_require_login_and_success_clears_attempts(self):
        self.client.logout()
        self.assertRedirects(self.client.get('/'), '/login/', fetch_redirect_response=False)
        self.client.post('/login/', {'username': 'owner', 'password': 'wrong'})
        self.assertEqual(LoginAttempt.objects.get().count, 1)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.post('/login/', {'username': 'owner', 'password': self.password}).status_code, 302)
        self.assertEqual(self.client.session['_auth_user_id'], str(self.user.pk))
        self.assertFalse(LoginAttempt.objects.exists())

    def test_login_rate_limit_and_expiry(self):
        self.client.logout()
        for _ in range(5):
            self.assertEqual(self.client.post('/login/', {'username': 'owner', 'password': 'wrong'}).status_code, 200)
        self.assertEqual(self.client.post('/login/', {'username': 'owner', 'password': self.password}).status_code, 429)
        LoginAttempt.objects.update(window=timezone.now()-timedelta(minutes=16))
        self.assertEqual(self.client.post('/login/', {'username': 'owner', 'password': self.password}).status_code, 302)

    def test_logout_requires_post_and_invalidates_session(self):
        self.assertEqual(self.client.get('/logout/').status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.post('/logout/').status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertEqual(self.client.get('/').status_code, 302)

    def test_password_change_keeps_session_and_replaces_password(self):
        new_password = 'replacement-password-9842'
        self.assertEqual(self.client.post('/password/', {'old_password': self.password,
            'new_password1': new_password, 'new_password2': new_password}).status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(self.password))
        self.assertEqual(self.client.get('/').status_code, 200)

    def test_csrf_required_for_login_and_authenticated_mutations(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/login/', {'username': 'owner', 'password': self.password}).status_code, 403)
        client.get('/login/')
        token = client.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertEqual(client.post('/login/', {'username': 'owner', 'password': self.password,
                                                 'csrfmiddlewaretoken': token}).status_code, 302)
        self.assertEqual(client.post('/nutrition/new/', self.food_data()).status_code, 403)
        self.assertFalse(FoodEntry.objects.exists())

    def test_all_core_pages_render_with_populated_records(self):
        plan = create_plan(self.user, self.plan_data())
        session = start_session(self.user, plan, 'Push')
        entry = FoodEntry.objects.create(user=self.user, name='Meal', calories=500)
        body = BodyMeasurement.objects.create(user=self.user, weight=80)
        paths = ['/', '/body/', '/nutrition/', '/nutrition/new/', f'/nutrition/{entry.pk}/',
                 '/targets/', '/workouts/', '/workouts/plan/', f'/workouts/session/{session.pk}/',
                 f'/workouts/set/{session.sets.first().pk}/', '/trends/', '/trends/?days=invalid',
                 '/settings/', '/password/', '/import/', f'/edit/body/{body.pk}/',
                 '/add/sleep/', '/add/cardio/', '/add/equipment/', '/add/exercise/', '/add/library/']
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)

    def test_dashboard_action_controls_use_spaced_groups(self):
        response = self.client.get('/')
        self.assertContains(
            response,
            '<div class="actions"><a class="button" href="/nutrition/new/">+ Log food</a><a class="subtle-link" href="/targets/">Set targets</a></div>',
            html=True,
        )
        self.assertContains(response, '<a class="button" href="/coach/">Open coach</a>', html=False)

    def test_trends_summary_cards(self):
        now = timezone.now()
        WorkoutSession.objects.create(user=self.user, name='A', started_at=now - timedelta(days=2))
        WorkoutSession.objects.create(user=self.user, name='B', started_at=now - timedelta(days=1), finished_at=now)
        FoodEntry.objects.create(user=self.user, name='M1', calories=1000, recorded_at=now - timedelta(days=5))
        FoodEntry.objects.create(user=self.user, name='M2', calories=1500, recorded_at=now - timedelta(days=3))
        FoodEntry.objects.create(user=self.user, name='M3', calories=2000, recorded_at=now - timedelta(days=1))
        SleepEntry.objects.create(user=self.user, date=(now - timedelta(days=2)).date(), hours=Decimal('7'))
        SleepEntry.objects.create(user=self.user, date=(now - timedelta(days=1)).date(), hours=Decimal('8'))
        BodyMeasurement.objects.create(user=self.user, weight=70, recorded_at=now - timedelta(days=4))
        BodyMeasurement.objects.create(user=self.user, weight=71, recorded_at=now - timedelta(days=2))
        BodyMeasurement.objects.create(user=self.user, weight=72, recorded_at=now - timedelta(days=1))

        response = self.client.get('/trends/?days=7')
        self.assertEqual(response.status_code, 200)
        summaries = response.context['summaries']
        self.assertEqual(len(summaries), 4)
        self.assertEqual([s['label'] for s in summaries], ['Workouts', 'Avg calories', 'Avg sleep', 'Weight change'])
        self.assertEqual(summaries[0]['value'], 2)
        self.assertEqual(summaries[0]['sub'], '2.0 per week')
        self.assertEqual(summaries[1]['value'], '1500 kcal')
        self.assertEqual(summaries[1]['sub'], '3 of 7 days logged')
        self.assertEqual(summaries[2]['value'], '7.5 h')
        self.assertEqual(summaries[2]['sub'], '2 nights recorded')
        self.assertEqual(summaries[3]['value'], '+2.0 kg')
        self.assertEqual(summaries[3]['sub'], '3 weigh-ins')

        empty = get_user_model().objects.create_user('empty')
        self.client.force_login(empty)
        response = self.client.get('/trends/?days=7')
        self.assertEqual(response.status_code, 200)
        summaries = response.context['summaries']
        self.assertEqual(len(summaries), 4)
        self.assertEqual(summaries[0]['value'], 0)
        self.assertEqual(summaries[0]['sub'], 'No sessions in this period')
        self.assertEqual(summaries[1]['value'], '—')
        self.assertEqual(summaries[1]['sub'], 'No food logged')
        self.assertEqual(summaries[2]['value'], '—')
        self.assertEqual(summaries[2]['sub'], '0 nights recorded')
        self.assertEqual(summaries[3]['value'], '—')
        self.assertEqual(summaries[3]['sub'], 'Add weigh-ins to see change')

    def test_nutrition_defaults_to_today_and_filters_by_date(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        y_start = timezone.make_aware(datetime.combine(yesterday, time.min))
        FoodEntry.objects.create(
            user=self.user, name='Yesterday meal', calories=300,
            protein=20, carbs=30, fat=10, fiber=2,
            recorded_at=y_start + timedelta(hours=12),
        )
        FoodEntry.objects.create(
            user=self.user, name='Today meal', calories=500,
            protein=40, carbs=60, fat=10, fiber=4,
        )
        response = self.client.get('/nutrition/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_date'], timezone.localdate())
        foods = list(response.context['foods'])
        self.assertEqual([f.name for f in foods], ['Today meal'])
        self.assertEqual(response.context['totals']['calories'], 500)

        response = self.client.get(f'/nutrition/?date={yesterday.isoformat()}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_date'], yesterday)
        foods = list(response.context['foods'])
        self.assertEqual([f.name for f in foods], ['Yesterday meal'])
        self.assertEqual(response.context['totals']['calories'], 300)

        response = self.client.get('/nutrition/?date=invalid')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_date'], timezone.localdate())
        foods = list(response.context['foods'])
        self.assertEqual([f.name for f in foods], ['Today meal'])

    def test_nutrition_filters_by_status_and_ignores_invalid_status(self):
        FoodEntry.objects.create(
            user=self.user, name='Manual entry', calories=200, state='manual',
        )
        FoodEntry.objects.create(
            user=self.user, name='AI entry', calories=300, state='ai_estimated',
        )
        response = self.client.get('/nutrition/?status=ai_estimated')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_status'], 'ai_estimated')
        foods = list(response.context['foods'])
        self.assertEqual(len(foods), 1)
        self.assertEqual(foods[0].name, 'AI entry')

        response = self.client.get('/nutrition/?status=bogus')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_status'], '')
        self.assertEqual(len(list(response.context['foods'])), 2)

    def test_nutrition_totals_incomplete_flag(self):
        FoodEntry.objects.create(user=self.user, name='Complete', calories=500, sugar=Decimal('10'), sodium=Decimal('500'))
        FoodEntry.objects.create(user=self.user, name='Missing sodium', calories=300, sugar=Decimal('5'))
        response = self.client.get('/nutrition/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['totals_incomplete'])

        FoodEntry.objects.filter(user=self.user, name='Missing sodium').update(sodium=Decimal('300'))
        response = self.client.get('/nutrition/')
        self.assertFalse(response.context['totals_incomplete'])

    def test_body_base_form_saves_without_advanced_fields(self):
        payload = {
            'recorded_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            'source': 'manual',
            'weight': '80',
        }
        self.assertEqual(self.client.post('/body/', payload).status_code, 302)
        measurement = BodyMeasurement.objects.get()
        self.assertEqual(measurement.weight, Decimal('80'))
        self.assertIsNone(measurement.body_fat)
        self.assertIsNone(measurement.muscle)
        self.assertIsNone(measurement.bmr)

    def test_body_advanced_form_saves_advanced_fields(self):
        payload = {
            'recorded_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            'source': 'manual',
            'weight': '80',
            'body_fat': '20',
            'advanced': '1',
            'muscle': '40.5',
            'bmr': '1600',
        }
        self.assertEqual(self.client.post('/body/', payload).status_code, 302)
        measurement = BodyMeasurement.objects.get()
        self.assertEqual(measurement.body_fat, Decimal('20'))
        self.assertEqual(measurement.muscle, Decimal('40.5'))
        self.assertEqual(measurement.bmr, Decimal('1600'))

    def test_body_edit_uses_advanced_form(self):
        measurement = BodyMeasurement.objects.create(
            user=self.user, weight=80, body_fat=20, muscle=40.5, bmr=1600,
        )
        response = self.client.get(f'/edit/body/{measurement.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Muscle')

    def test_body_context_latest_summary(self):
        first = BodyMeasurement.objects.create(
            user=self.user, weight=80, body_fat=20,
            recorded_at=timezone.now() - timedelta(hours=2),
        )
        second = BodyMeasurement.objects.create(
            user=self.user, weight=79, body_fat=19,
            recorded_at=timezone.now(),
        )
        response = self.client.get('/body/')
        self.assertEqual(response.status_code, 200)
        latest = response.context['latest']
        self.assertEqual(latest['weight'], second.weight)
        self.assertEqual(latest['body_fat'], second.body_fat)
        self.assertEqual(latest['source'], second.source)

    def test_plan_day_shows_exercises_and_today(self):
        plan = create_plan(self.user, self.plan_data(schedule=['Push', 'Pull', 'Rest']))
        response = self.client.get('/workouts/day/Push/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['day_name'], 'Push')
        self.assertTrue(response.context['is_today'])
        exercises = response.context['day_exercises']
        self.assertEqual(len(exercises), 1)
        self.assertEqual(exercises[0]['name'], 'Bench press')
        self.assertEqual(response.context['plan'], plan)

        self.assertEqual(self.client.get('/workouts/day/Nope/').status_code, 404)

    def test_plan_day_add_and_remove_exercise(self):
        plan = create_plan(self.user, self.plan_data(schedule=['Push', 'Rest']))
        squat = Exercise.objects.create(user=self.user, name='Squat', primary_muscles=['Quads'])
        response = self.client.post('/workouts/day/Push/', {
            'action': 'add',
            'exercise': str(squat.pk),
            'sets': '3',
            'rep_min': '8',
            'rep_max': '12',
            'rest': '90',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkoutPlan.objects.count(), 2)
        latest = WorkoutPlan.objects.first()
        self.assertEqual(len(latest.exercises), 2)
        added = latest.exercises[1]
        self.assertEqual(added['exercise'], str(squat.pk))
        self.assertEqual(added['sets'], 3)

        response = self.client.post('/workouts/day/Push/', {
            'action': 'remove',
            'index': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkoutPlan.objects.count(), 3)
        latest = WorkoutPlan.objects.first()
        self.assertEqual(len(latest.exercises), 1)

        plan.refresh_from_db()
        self.assertEqual(len(plan.exercises), 1)

    def test_plan_day_add_validates_via_create_plan(self):
        create_plan(self.user, self.plan_data(schedule=['Push', 'Rest']))
        other = get_user_model().objects.create_user('other')
        foreign = Exercise.objects.create(user=other, name='Foreign', primary_muscles=['Back'])
        response = self.client.post('/workouts/day/Push/', {
            'action': 'add',
            'exercise': str(foreign.pk),
            'sets': '3',
            'rep_min': '8',
            'rep_max': '12',
            'rest': '90',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkoutPlan.objects.count(), 1)

        response = self.client.post('/workouts/day/Push/', {
            'action': 'add',
            'exercise': str(self.exercise.pk),
            'sets': '0',
            'rep_min': '8',
            'rep_max': '12',
            'rest': '90',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(WorkoutPlan.objects.count(), 1)

    def test_plan_edit_preserves_exercises(self):
        import json
        plan = create_plan(self.user, self.plan_data(schedule=['Push', 'Rest']))
        response = self.client.post('/workouts/plan/', {
            'name': plan.name,
            'schedule_type': plan.schedule_type,
            'schedule': json.dumps(plan.schedule),
            'exercises': json.dumps(plan.exercises),
            'version': str(plan.version),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkoutPlan.objects.count(), 2)
        latest = WorkoutPlan.objects.first()
        self.assertEqual(latest.exercises, plan.exercises)

    # ── Training activity heatmap + streak ──────────────────────────────

    def test_training_activity_levels_and_streak(self):
        from core.services import training_activity
        plan = create_plan(self.user, self.plan_data())
        session = start_session(self.user, plan, 'Push')
        for s in session.sets.all():
            s.completed = True
            s.save(update_fields=['completed'])
        activity = training_activity(self.user)
        flat = [d for week in activity['weeks'] for d in week]
        today_cell = [d for d in flat if d['iso'] == timezone.localdate().isoformat()]
        self.assertEqual(len(today_cell), 1)
        self.assertGreaterEqual(today_cell[0]['level'], 1)
        self.assertEqual(activity['streak'], 1)

    def test_training_activity_streak_counts_consecutive_days(self):
        from core.services import training_activity
        from datetime import timedelta as _td
        for offset in (0, 1, 2):
            day = timezone.now() - _td(days=offset)
            session = WorkoutSession.objects.create(user=self.user, name='S', started_at=day)
            WorkoutSet.objects.create(
                session=session, exercise=self.exercise, weight=60, reps=8,
                set_type='working', completed=True,
            )
        activity = training_activity(self.user)
        self.assertEqual(activity['streak'], 3)

    def test_training_activity_ignores_incomplete_and_warmup(self):
        from core.services import training_activity
        session = WorkoutSession.objects.create(user=self.user, name='S')
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=60, reps=8, completed=False)
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=40, reps=8, set_type='warmup', completed=True)
        activity = training_activity(self.user)
        self.assertEqual(activity['streak'], 0)
        today = timezone.localdate().isoformat()
        self.assertFalse(any(d['level'] for w in activity['weeks'] for d in w if d['iso'] == today))

    def test_training_activity_counts_completed_cardio(self):
        # A cardio-only session is still a training day.
        from core.services import training_activity
        from core.models import WorkoutCardio
        session = WorkoutSession.objects.create(user=self.user, name='Cardio day')
        cardio_ex = Exercise.objects.create(user=self.user, name='Rowing', activity_type='cardio')
        WorkoutCardio.objects.create(session=session, exercise=cardio_ex, minutes=25, completed=True)
        activity = training_activity(self.user)
        self.assertEqual(activity['streak'], 1)
        today = timezone.localdate().isoformat()
        today_cell = [d for w in activity['weeks'] for d in w if d['iso'] == today]
        self.assertEqual(today_cell[0]['level'], 1)

    # ── Personal records ────────────────────────────────────────────────

    def test_personal_records_epley_best_and_top_sets(self):
        from core.services import personal_records
        session = WorkoutSession.objects.create(user=self.user, name='S')
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=100, reps=5, set_type='working', completed=True)
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=90, reps=8, set_type='working', completed=True)
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=140, reps=2, set_type='drop', completed=True)
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=40, reps=10, set_type='warmup', completed=True)
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=80, reps=3, set_type='working', completed=False)
        records = personal_records(self.user)
        self.assertEqual(len(records), 1)
        r = records[0]
        # 90×8 e1rm=114 > 100×5 e1rm=116.7? No: 100×5 = 116.7 wins.
        self.assertEqual((r['weight'], r['reps']), (100, 5))
        self.assertAlmostEqual(r['e1rm'], round(100 * (1 + 5 / 30), 1))
        # Only completed working sets appear in the top list.
        self.assertEqual(len(r['top_sets']), 2)

    def test_is_personal_record_and_flash_on_complete(self):
        from core.services import is_personal_record
        session = WorkoutSession.objects.create(user=self.user, name='S')
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=80, reps=5, set_type='working', completed=True)
        # New set completing above the old best is a PR.
        new_set = WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=100, reps=5, set_type='working')
        self.assertTrue(is_personal_record(self.user, self.exercise.pk, 100, 5))
        self.assertFalse(is_personal_record(self.user, self.exercise.pk, 80, 5))
        response = self.client.post(f'/workouts/set/{new_set.pk}/complete/')
        self.assertEqual(response.status_code, 302)
        messages_list = list(get_messages(response.wsgi_request))
        self.assertTrue(any('New PR' in str(m) for m in messages_list))

    def test_prs_page_renders(self):
        from core.services import personal_records
        session = WorkoutSession.objects.create(user=self.user, name='S')
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=100, reps=5, set_type='working', completed=True)
        response = self.client.get('/workouts/prs/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Personal records')
        self.assertContains(response, self.exercise.name)

    def test_personal_records_progress_chart_points(self):
        from core.services import personal_records
        from datetime import timedelta as _td
        session1 = WorkoutSession.objects.create(user=self.user, name='S1', started_at=timezone.now() - _td(days=14))
        session2 = WorkoutSession.objects.create(user=self.user, name='S2', started_at=timezone.now() - _td(days=7))
        WorkoutSet.objects.create(session=session1, exercise=self.exercise, weight=80, reps=5, set_type='working', completed=True)
        WorkoutSet.objects.create(session=session2, exercise=self.exercise, weight=90, reps=5, set_type='working', completed=True)
        records = personal_records(self.user)
        r = records[0]
        self.assertEqual(len(r['progress']), 2)
        self.assertIn(',', r['chart'])
        pts = r['chart'].split(' ')
        self.assertEqual(len(pts), 2)
        # Later heavier point must sit higher (smaller y) on the chart.
        self.assertLess(int(pts[1].split(',')[1]), int(pts[0].split(',')[1]))

    def test_prs_effort_strip_data(self):
        from core.services import personal_records
        session = WorkoutSession.objects.create(user=self.user, name='S')
        WorkoutSet.objects.create(session=session, exercise=self.exercise, weight=100, reps=5, set_type='working', completed=True, rpe=8.5, rir=2)
        records = personal_records(self.user)
        self.assertEqual(len(records[0]['effort']), 1)
        self.assertEqual(records[0]['effort'][0]['rpe'], 8.5)
        self.assertEqual(records[0]['effort'][0]['rir'], 2.0)

    def test_streak_freeze_on_planned_rest_days(self):
        # Fixed plan resting on Sundays: a Sunday gap must not break the streak.
        from core.services import training_activity
        from core.models import WorkoutPlan
        from datetime import datetime as _dt
        today = timezone.localdate()
        # Most recent Sunday, and the days around it that WERE trained.
        sunday = today - timedelta(days=(today.weekday() + 1) % 7 or 7)
        saturday = sunday - timedelta(days=1)
        monday_after = sunday + timedelta(days=1)
        WorkoutPlan.objects.create(
            user=self.user, name='P', version=1, schedule_type='fixed',
            schedule={str(i): 'Train' for i in range(6)} | {'6': 'Rest'},
            exercises=[],
        )
        trained_days = [saturday, monday_after]
        # Also train every day from monday_after up to yesterday so the
        # streak is unbroken from saturday to now.
        d = monday_after
        while d < today:
            trained_days.append(d)
            d += timedelta(days=1)
        for day in trained_days:
            at = timezone.make_aware(_dt(day.year, day.month, day.day, 12, 0))
            s = WorkoutSession.objects.create(user=self.user, name='S', started_at=at)
            WorkoutSet.objects.create(session=s, exercise=self.exercise, weight=60, reps=8, set_type='working', completed=True)
        activity = training_activity(self.user)
        # Saturday trained, Sunday frozen, then every day after → streak
        # counts the trained days.
        expected = len(set(trained_days))
        self.assertEqual(activity['streak'], expected)
        sunday_cell = [d for w in activity['weeks'] for d in w if d['iso'] == sunday.isoformat()]
        self.assertEqual(sunday_cell[0]['level'], 'rest')

    def test_unplanned_gap_still_breaks_streak(self):
        from core.services import training_activity
        from datetime import datetime as _dt
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        three_days_ago = today - timedelta(days=3)  # gap at two days ago
        for day in (yesterday, three_days_ago):
            at = timezone.make_aware(_dt(day.year, day.month, day.day, 12, 0))
            s = WorkoutSession.objects.create(user=self.user, name='S', started_at=at)
            WorkoutSet.objects.create(session=s, exercise=self.exercise, weight=60, reps=8, set_type='working', completed=True)
        activity = training_activity(self.user)
        # The unplanned skip two days ago caps the streak at yesterday only.
        self.assertEqual(activity['streak'], 1)

    def test_body_tape_measurements_saved_and_charted(self):
        from core.models import BodyMeasurement
        # Advanced form now includes waist/arm/thigh; verify persistence + trends series.
        response = self.client.post('/body/', data={
            'advanced': '1',
            'recorded_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
            'source': 'manual', 'weight': '80',
            'waist': '85.5', 'arm': '36', 'thigh': '58',
        })
        self.assertEqual(response.status_code, 302)
        entry = BodyMeasurement.objects.filter(user=self.user, waist__isnull=False).first()
        self.assertIsNotNone(entry)
        self.assertEqual(float(entry.waist), 85.5)
        self.assertEqual(float(entry.arm), 36.0)
        self.assertEqual(float(entry.thigh), 58.0)
        trends = self.client.get('/trends/?days=7')
        self.assertEqual(trends.status_code, 200)
        import json as _json
        import re as _re
        m = _re.search(r'id="chart-data"[^>]*>(.*?)</script>', trends.content.decode())
        charts = _json.loads(m.group(1))
        self.assertTrue(any('Waist' in k for k in charts))
        self.assertTrue(any('Arm' in k for k in charts))
        waist_key = next(k for k in charts if 'Waist' in k)
        self.assertEqual(len(charts[waist_key]), 1)
        self.assertEqual(charts[waist_key][0]['value'], 85.5)


    def test_training_activity_counts_after_midnight_local(self):
        # Regression: TruncDate defaulted to UTC, so a session logged at
        # 00:30 Bangkok (= 17:30 UTC the previous day) landed on the wrong
        # heatmap day. It must count as its LOCAL date.
        from core.services import training_activity
        from datetime import datetime as _dt
        now = timezone.localtime()
        # Yesterday 00:30 local — inside the grid, before-7am edge case.
        yday = (now - timedelta(days=1)).replace(hour=0, minute=30, second=0, microsecond=0)
        s = WorkoutSession.objects.create(user=self.user, name='Late', started_at=yday)
        WorkoutSet.objects.create(session=s, exercise=self.exercise, weight=60, reps=8,
                                  set_type='working', completed=True)
        activity = training_activity(self.user, days=7)
        iso = yday.date().isoformat()
        cell = [d for w in activity['weeks'] for d in w if d['iso'] == iso]
        self.assertTrue(cell and cell[0]['level'] in (1, 2, 3, 4),
                        f"session on {iso} should light up (got {cell})")

    def test_diary_shows_latest_job_status(self):
        from coaching.models import Job
        entry = FoodEntry.objects.create(user=self.user, name='Job meal', calories=0,
                                         protein=0, carbs=0, fat=0, fiber=0)
        Job.objects.create(user=self.user, task='food', status='failed',
                           payload={'entry': str(entry.pk)}, dedupe='d1')
        response = self.client.get('/nutrition/')
        html = response.content.decode()
        self.assertIn('AI failed', html)
        self.assertIn('Retry analysis', html)
        self.assertIn(f'/coach/retry/', html)

    def test_set_edit_form_excludes_cardio_exercises(self):
        # Strength set editor must only offer strength exercises.
        plan = create_plan(self.user, self.plan_data())
        session = start_session(self.user, plan, 'Push')
        item = session.sets.first()
        cardio_ex = Exercise.objects.create(user=self.user, name='Rowing', activity_type='cardio')
        response = self.client.get(f'/workouts/set/{item.pk}/')
        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        offered = list(form.fields['exercise'].queryset.values_list('pk', flat=True))
        self.assertNotIn(cardio_ex.pk, offered)
        self.assertIn(self.exercise.pk, offered)
