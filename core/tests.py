from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from core.models import BodyMeasurement, FoodEntry, WorkoutPlan, Exercise
from core.services import create_target, create_plan, active_target, retain_images


class DomainTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "owner", password="a sufficiently long test password"
        )

    def test_target_versions_and_stale_prevention(self):
        data = dict(calories=2000, protein=140, carbs=225, fat=60, fiber=30)
        a = create_target(self.user, data)
        b = create_target(
            self.user, {**data, "calories": 2100}, expected_version=a.version
        )
        self.assertEqual(active_target(self.user).pk, b.pk)
        a.refresh_from_db()
        self.assertEqual(a.calories, 2000)
        with self.assertRaises(ValidationError):
            create_target(self.user, data, expected_version=1)

    def test_sources_coexist(self):
        BodyMeasurement.objects.create(user=self.user, source="smart_scale", bmr=1700)
        BodyMeasurement.objects.create(user=self.user, source="calculated", bmr=1650)
        self.assertEqual(BodyMeasurement.objects.count(), 2)

    def test_plan_validates_exercise_reference(self):
        with self.assertRaises(ValidationError):
            create_plan(
                self.user,
                dict(
                    name="Push",
                    schedule_type="rotation",
                    schedule=["Push"],
                    exercises=[{"exercise": "bad"}],
                ),
            )

    def test_auth_and_csrf(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        c = Client(enforce_csrf_checks=True)
        self.assertEqual(
            c.post("/login/", {"username": "owner", "password": "bad"}).status_code, 403
        )

    def test_rate_limit(self):
        for _ in range(5):
            self.client.post("/login/", {"username": "owner", "password": "bad"})
        self.assertEqual(
            self.client.post(
                "/login/", {"username": "owner", "password": "bad"}
            ).status_code,
            429,
        )
