"""Regressions for user-edited food breakdowns (schema 2).

Covers the 2026-09-21 production incident: a blank custom ingredient row
voided every total (zeroed NOT NULL columns = data loss), hand-entered
values vanished on reload, unmatched majors could never be resolved, and
CSP (script-src 'self') silently killed the delete button's inline JS.
"""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import FoodEntry
from .nutrition_calc import compute_meal


@override_settings(
    SECURE_SSL_REDIRECT=False, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False,
    ALLOWED_HOSTS=['testserver'],
    STORAGES={
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'},
    },
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
)
class FoodBreakdownTests(TestCase):
    password = 'test-owner-long-password'

    def setUp(self):
        self.user = get_user_model().objects.create_user('owner', password=self.password)
        self.client.force_login(self.user)

    def food_data(self, **changes):
        data = dict({'recorded_at': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
                     'name': 'Rice and pork', 'quantity': '1 plate', 'calories': '500',
                     'protein': '40', 'carbs': '60', 'fat': '10', 'fiber': '4', 'state': 'confirmed'}, **changes)
        return data

    def entry(self, **kwargs):
        defaults = dict(user=self.user, name='Rice and pork', quantity='1 plate',
                        calories=500, protein=40, carbs=60, fat=10, fiber=4,
                        state='confirmed')
        defaults.update(kwargs)
        return FoodEntry.objects.create(**defaults)

    # ── compute_meal unit regressions ─────────────────────────────────

    def test_blank_custom_row_does_not_void_totals(self):
        """A name-only custom row must not zero out known reference totals."""
        computed = compute_meal([
            {'ref_key': 'cooked_white_rice', 'name_th': 'ข้าวสวยสุก', 'weight_g': 180,
             'min_g': 140, 'max_g': 220},
            {'ref_key': 'custom', 'name_th': 'หมูทอดติดมัน', 'weight_g': 100,
             'min_g': 0, 'max_g': 2000},
        ])
        self.assertEqual(computed['totals']['kcal'], 234.0)
        self.assertEqual(computed['totals']['carbs'], 50.4)
        # ...but the gap is flagged, not hidden.
        self.assertIn('kcal', computed['unknown_fields'])

    def test_custom_values_round_trip_and_reference_override(self):
        """Hand-entered values echo back per item; a reference row keeps its
        other reference values when one cell is overridden."""
        computed = compute_meal([
            {'ref_key': 'custom', 'name_th': 'น้ำจิ้ม', 'weight_g': 30,
             'custom_values': {'kcal': 60, 'sodium': 900}},
            {'ref_key': 'cooked_white_rice', 'name_th': 'ข้าวสวยสุก', 'weight_g': 180,
             'custom_values': {'kcal': 250}},
        ])
        custom = computed['ingredients'][0]
        self.assertEqual(custom['custom_values']['kcal'], 60.0)
        self.assertEqual(custom['computed']['kcal'], 60.0)
        # Overridden kcal, reference-derived protein and carbs survive.
        rice = computed['ingredients'][1]
        self.assertEqual(rice['computed']['kcal'], 250.0)
        self.assertEqual(rice['computed']['protein'], 4.86)
        self.assertEqual(rice['computed']['carbs'], 50.4)
        self.assertEqual(computed['totals']['kcal'], 310.0)

    # ── save flow regressions (POST /nutrition/<pk>/) ─────────────────

    def _post_save(self, entry, payload):
        return self.client.post(
            f'/nutrition/{entry.pk}/',
            data=dict(self.food_data(), breakdown_json=json.dumps(payload)),
        )

    def test_save_with_blank_custom_keeps_form_values(self):
        entry = self.entry()
        payload = {'dish_name': 'Rice and pork', 'items': [
            {'ref_key': 'custom', 'name_th': 'หมูทอดติดมัน', 'weight_g': 100},
        ]}
        response = self._post_save(entry, payload)
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        # Unresolvable totals keep the submitted values instead of zeroing.
        self.assertEqual(float(entry.calories), 500.0)
        self.assertEqual(float(entry.protein), 40.0)

    def test_adding_valued_custom_resolves_unmatched_major(self):
        entry = self.entry()
        payload = {
            'dish_name': 'Rice and pork', 'strategy': 'components',
            'items': [
                {'ref_key': 'cooked_white_rice', 'name_th': 'ข้าวสวยสุก', 'weight_g': 180,
                 'min_g': 140, 'max_g': 220},
                {'ref_key': 'custom', 'name_th': 'หมูทอดติดมัน', 'weight_g': 100,
                 'custom_values': {'kcal': 250, 'protein': 20}},
            ],
            'unmatched': [{'name_th': 'หมูทอดติดมัน', 'estimated_share': 'major',
                           'note': 'no reference'}],
        }
        response = self._post_save(entry, payload)
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.ai_breakdown['completeness'], 'complete')
        self.assertEqual(entry.ai_breakdown['unmatched'], [])
        self.assertEqual(float(entry.calories), 484.0)
        self.assertNotIn('INCOMPLETE', entry.uncertainty)

    def test_name_only_custom_does_not_resolve_major(self):
        entry = self.entry()
        payload = {
            'dish_name': 'Rice and pork',
            'items': [
                {'ref_key': 'cooked_white_rice', 'name_th': 'ข้าวสวยสุก', 'weight_g': 180},
                {'ref_key': 'custom', 'name_th': 'หมูทอดติดมัน', 'weight_g': 100},
            ],
            'unmatched': [{'name_th': 'หมูทอดติดมัน', 'estimated_share': 'major'}],
        }
        self._post_save(entry, payload)
        entry.refresh_from_db()
        self.assertEqual(entry.ai_breakdown['completeness'], 'incomplete')
        self.assertTrue(entry.uncertainty.startswith('INCOMPLETE —'))

    def test_incomplete_prefix_does_not_stack(self):
        entry = self.entry()
        payload = {
            'dish_name': 'Rice and pork',
            'items': [{'ref_key': 'custom', 'name_th': 'หมูทอดติดมัน', 'weight_g': 100}],
            'unmatched': [{'name_th': 'หมูทอดติดมัน', 'estimated_share': 'major'}],
        }
        self._post_save(entry, payload)
        self._post_save(entry, payload)
        entry.refresh_from_db()
        self.assertEqual(entry.uncertainty.count('INCOMPLETE'), 1)

    def test_malformed_numbers_do_not_500(self):
        entry = self.entry()
        payload = {'dish_name': 'x', 'items': [
            {'ref_key': 'custom', 'name_th': 'junk', 'weight_g': 'abc'},
            {'ref_key': 'cooked_white_rice', 'name_th': 'ข้าวสวยสุก', 'weight_g': 180},
        ]}
        response = self._post_save(entry, payload)
        self.assertEqual(response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(float(entry.calories), 234.0)

    # ── CSP regressions: no inline JS on food pages ────────────────────

    def test_food_form_delete_uses_form_attribute_no_inline_js(self):
        entry = self.entry(ai_breakdown={'schema': 2, 'dish_name': 'Rice and pork',
                                         'items': [], 'unmatched': [],
                                         'completeness': 'complete'})
        response = self.client.get(f'/nutrition/{entry.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'form="delete-food-{entry.pk}"', response.content.decode())
        self.assertNotIn('onclick=', response.content.decode())
        self.assertNotIn('function deleteFood', response.content.decode())

    def test_diary_page_has_no_inline_handlers(self):
        self.entry()
        response = self.client.get('/nutrition/')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('onclick=', response.content.decode())
