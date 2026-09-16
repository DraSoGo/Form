"""Domain and browser regressions without external services or shared media."""
import io
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from PIL import Image
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import (
    BodyMeasurement, Exercise, FoodEntry, FoodLibrary, LoginAttempt,
    MealTemplate, NutritionTarget, Profile, WorkoutPlan, WorkoutSession, WorkoutSet,
)
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
        return dict(name='Training', schedule_type='rotation', schedule=['Push', 'Rest'],
                    exercises=[{'exercise': str(self.exercise.pk), 'day': 'Push', 'sets': 2,
                                'rep_min': 6, 'rep_max': 10, 'rest': 120}], **changes)

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
        self.assertEqual(weekly_volume(self.user), {'Chest': {'direct': 2, 'indirect': 0},
                                                   'Triceps': {'direct': 0, 'indirect': 2}})

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
