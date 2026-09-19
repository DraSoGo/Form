"""Tests for core.muscles muscle-map logic."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from .models import Exercise, WorkoutSession, WorkoutSet
from .muscles import (
    ALIASES,
    MUSCLES,
    REGIONS,
    muscle_summary,
    normalize,
    recovery_by_muscle,
    region_states,
    volume_by_muscle,
)


class MuscleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("lifter", password="pw")

    def test_normalize_maps_aliases_and_ignores_case_and_space(self):
        self.assertEqual(normalize("  Chest "), "chest")
        self.assertEqual(normalize("PECTORALS"), "chest")
        self.assertEqual(normalize("pecs"), "chest")
        self.assertEqual(normalize("Traps"), "back")
        self.assertEqual(normalize("rear delts"), "shoulders")
        self.assertEqual(normalize("Quadriceps"), "quads")
        self.assertEqual(normalize("obliques"), "abs")
        self.assertIsNone(normalize("unknown"))
        self.assertIsNone(normalize(""))

    def test_volume_counts_primary_and_secondary_and_excludes_warmup_uncompleted(self):
        chest = Exercise.objects.create(
            user=self.user,
            name="Bench press",
            primary_muscles=["chest"],
            secondary_muscles=["triceps"],
        )
        back = Exercise.objects.create(
            user=self.user,
            name="Row",
            primary_muscles=["back"],
        )
        session = WorkoutSession.objects.create(user=self.user, name="Push")
        WorkoutSet.objects.create(
            session=session, exercise=chest, completed=True, set_type="working"
        )
        WorkoutSet.objects.create(
            session=session, exercise=chest, completed=True, set_type="drop"
        )
        WorkoutSet.objects.create(
            session=session, exercise=chest, completed=False, set_type="working"
        )
        WorkoutSet.objects.create(
            session=session, exercise=back, completed=True, set_type="warmup"
        )
        volume = volume_by_muscle(self.user)
        self.assertEqual(volume["chest"]["sets"], 2)
        self.assertEqual(volume["triceps"]["sets"], 2)
        self.assertEqual(volume["back"]["sets"], 0)
        for muscle in MUSCLES:
            self.assertIn(muscle, volume)

    def test_volume_level_thresholds(self):
        chest = Exercise.objects.create(
            user=self.user, name="Fly", primary_muscles=["chest"]
        )
        back = Exercise.objects.create(
            user=self.user, name="Row", primary_muscles=["back"]
        )
        quads = Exercise.objects.create(
            user=self.user, name="Squat", primary_muscles=["quads"]
        )
        session = WorkoutSession.objects.create(user=self.user, name="Test")
        WorkoutSet.objects.create(session=session, exercise=chest, completed=True)
        for _ in range(6):
            WorkoutSet.objects.create(session=session, exercise=back, completed=True)
        for _ in range(12):
            WorkoutSet.objects.create(session=session, exercise=quads, completed=True)
        volume = volume_by_muscle(self.user)
        self.assertEqual((volume["biceps"]["sets"], volume["biceps"]["level"]), (0, 0))
        self.assertEqual((volume["chest"]["sets"], volume["chest"]["level"]), (1, 1))
        self.assertEqual((volume["back"]["sets"], volume["back"]["level"]), (6, 2))
        self.assertEqual((volume["quads"]["sets"], volume["quads"]["level"]), (12, 3))

    def test_volume_ignores_cardio_and_counts_archived_exercises(self):
        strength = Exercise.objects.create(
            user=self.user,
            name="Curl",
            primary_muscles=["biceps"],
            archived=True,
        )
        cardio = Exercise.objects.create(
            user=self.user,
            name="Run",
            activity_type="cardio",
            default_minutes=30,
        )
        session = WorkoutSession.objects.create(user=self.user, name="Mix")
        WorkoutSet.objects.create(session=session, exercise=strength, completed=True)
        WorkoutSet.objects.create(session=session, exercise=cardio, completed=True)
        volume = volume_by_muscle(self.user)
        self.assertEqual(volume["biceps"]["sets"], 1)

    def test_volume_respects_days_window(self):
        exercise = Exercise.objects.create(
            user=self.user, name="Press", primary_muscles=["shoulders"]
        )
        old_session = WorkoutSession.objects.create(
            user=self.user,
            name="Old",
            started_at=timezone.now() - timedelta(days=8),
        )
        new_session = WorkoutSession.objects.create(
            user=self.user, name="New", started_at=timezone.now()
        )
        WorkoutSet.objects.create(session=old_session, exercise=exercise, completed=True)
        WorkoutSet.objects.create(session=new_session, exercise=exercise, completed=True)
        volume = volume_by_muscle(self.user, days=7)
        self.assertEqual(volume["shoulders"]["sets"], 1)

    def test_recovery_states(self):
        chest = Exercise.objects.create(
            user=self.user, name="Bench", primary_muscles=["chest"]
        )
        back = Exercise.objects.create(
            user=self.user, name="Row", primary_muscles=["back"]
        )
        quads = Exercise.objects.create(
            user=self.user, name="Squat", primary_muscles=["quads"]
        )
        recent = WorkoutSession.objects.create(
            user=self.user, name="Today", started_at=timezone.now()
        )
        recovering = WorkoutSession.objects.create(
            user=self.user,
            name="Yesterday",
            started_at=timezone.now() - timedelta(days=1),
        )
        fresh = WorkoutSession.objects.create(
            user=self.user,
            name="Three days ago",
            started_at=timezone.now() - timedelta(days=3),
        )
        WorkoutSet.objects.create(session=recent, exercise=chest, completed=True)
        WorkoutSet.objects.create(session=recovering, exercise=back, completed=True)
        WorkoutSet.objects.create(session=fresh, exercise=quads, completed=True)
        recovery = recovery_by_muscle(self.user)
        self.assertEqual(recovery["chest"], {"days_ago": 0, "state": "recent"})
        self.assertEqual(recovery["back"], {"days_ago": 1, "state": "recovering"})
        self.assertEqual(recovery["quads"], {"days_ago": 3, "state": "fresh"})
        self.assertEqual(recovery["biceps"], {"days_ago": None, "state": "unknown"})
        for muscle in MUSCLES:
            self.assertIn(muscle, recovery)

    def test_regions_are_strings_with_no_duplicates(self):
        all_regions = []
        for muscle in MUSCLES:
            self.assertIn(muscle, REGIONS)
            all_regions.extend(REGIONS[muscle])
        self.assertTrue(all(isinstance(r, str) for r in all_regions))
        self.assertEqual(len(all_regions), len(set(all_regions)))

    def test_region_states_intensity_mapping(self):
        chest = Exercise.objects.create(
            user=self.user, name="Fly", primary_muscles=["chest"]
        )
        quads = Exercise.objects.create(
            user=self.user, name="Squat", primary_muscles=["quads"]
        )
        session = WorkoutSession.objects.create(user=self.user, name="Test")
        for _ in range(4):
            WorkoutSet.objects.create(session=session, exercise=chest, completed=True)
        for _ in range(13):
            WorkoutSet.objects.create(session=session, exercise=quads, completed=True)
        states = region_states(self.user)
        for region in REGIONS["chest"]:
            self.assertEqual(states[region], 3)
        for region in REGIONS["quads"]:
            self.assertEqual(states[region], 8)
        for region in REGIONS["biceps"]:
            self.assertEqual(states[region], 0)
        self.assertEqual(len(states), sum(len(v) for v in REGIONS.values()))

    def test_muscle_summary_direct_and_indirect(self):
        chest = Exercise.objects.create(
            user=self.user,
            name="Bench",
            primary_muscles=["chest"],
            secondary_muscles=["triceps"],
        )
        session = WorkoutSession.objects.create(user=self.user, name="Push")
        WorkoutSet.objects.create(session=session, exercise=chest, completed=True, set_type="working")
        WorkoutSet.objects.create(session=session, exercise=chest, completed=True, set_type="drop")
        WorkoutSet.objects.create(session=session, exercise=chest, completed=True, set_type="warmup")
        WorkoutSet.objects.create(session=session, exercise=chest, completed=False, set_type="working")
        self.assertEqual(muscle_summary(self.user, "chest"), {"direct": 2, "indirect": 0})
        self.assertEqual(muscle_summary(self.user, "triceps"), {"direct": 0, "indirect": 2})

    def test_muscle_summary_respects_days_window(self):
        exercise = Exercise.objects.create(
            user=self.user, name="Press", primary_muscles=["shoulders"]
        )
        old_session = WorkoutSession.objects.create(
            user=self.user,
            name="Old",
            started_at=timezone.now() - timedelta(days=8),
        )
        new_session = WorkoutSession.objects.create(
            user=self.user, name="New", started_at=timezone.now()
        )
        WorkoutSet.objects.create(session=old_session, exercise=exercise, completed=True)
        WorkoutSet.objects.create(session=new_session, exercise=exercise, completed=True)
        self.assertEqual(muscle_summary(self.user, "shoulders", days=7), {"direct": 1, "indirect": 0})
