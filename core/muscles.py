"""Muscle Map logic.

These helpers estimate training load and recovery state from logged sets.
They are not medical or physiological measurements.
"""

from datetime import timedelta

from django.utils import timezone

from .models import WorkoutSet

MUSCLES = [
    "chest",
    "back",
    "shoulders",
    "biceps",
    "triceps",
    "abs",
    "glutes",
    "quads",
    "hamstrings",
    "calves",
]

# body-muscles asset region IDs (https://github.com/vulovix/body-muscles)
REGIONS = {
    "chest": [
        "chest-upper-left",
        "chest-upper-right",
        "chest-lower-left",
        "chest-lower-right",
    ],
    "back": [
        "lats-upper-left",
        "lats-upper-right",
        "lats-mid-left",
        "lats-mid-right",
        "lats-lower-left",
        "lats-lower-right",
        "traps-mid-left",
        "traps-mid-right",
        "traps-lower-left",
        "traps-lower-right",
        "lower-back-erectors-left",
        "lower-back-erectors-right",
        "spine",
    ],
    "shoulders": [
        "shoulder-front-left",
        "shoulder-front-right",
        "shoulder-side-left",
        "shoulder-side-right",
        "deltoid-rear-left",
        "deltoid-rear-right",
    ],
    "biceps": ["biceps-left", "biceps-right"],
    "triceps": [
        "triceps-long-left",
        "triceps-long-right",
        "triceps-lateral-left",
        "triceps-lateral-right",
    ],
    "abs": [
        "abs-upper-left",
        "abs-upper-right",
        "abs-lower-left",
        "abs-lower-right",
        "obliques-left",
        "obliques-right",
    ],
    "glutes": [
        "gluteus-maximus-left",
        "gluteus-maximus-right",
        "gluteus-medius-left",
        "gluteus-medius-right",
    ],
    "quads": ["quads-left", "quads-right"],
    "hamstrings": [
        "hamstrings-lateral-left",
        "hamstrings-lateral-right",
        "hamstrings-medial-left",
        "hamstrings-medial-right",
    ],
    "calves": [
        "calves-gastroc-lateral-left",
        "calves-gastroc-lateral-right",
        "calves-gastroc-medial-left",
        "calves-gastroc-medial-right",
        "calves-soleus-left",
        "calves-soleus-right",
    ],
}

ALIASES = {
    "chest": "chest",
    "pectorals": "chest",
    "pecs": "chest",
    "back": "back",
    "lats": "back",
    "lower back": "back",
    "traps": "back",
    "shoulders": "shoulders",
    "delts": "shoulders",
    "front delts": "shoulders",
    "side delts": "shoulders",
    "rear delts": "shoulders",
    "biceps": "biceps",
    "triceps": "triceps",
    "abs": "abs",
    "core": "abs",
    "obliques": "abs",
    "abdominals": "abs",
    "glutes": "glutes",
    "quads": "quads",
    "quadriceps": "quads",
    "hamstrings": "hamstrings",
    "calves": "calves",
}


def normalize(name):
    """Return the canonical muscle key for a raw name, or None."""
    key = str(name).strip().lower()
    return ALIASES.get(key)


def _level(sets):
    if sets == 0:
        return 0
    if sets <= 5:
        return 1
    if sets <= 11:
        return 2
    return 3


def _intensity(sets):
    if sets == 0:
        return 0
    if sets <= 2:
        return 2
    if sets <= 5:
        return 3
    if sets <= 8:
        return 5
    if sets <= 11:
        return 6
    if sets <= 15:
        return 8
    return 10


def _set_counts(user, days=7):
    """Return raw completed, non-warmup set counts per canonical muscle."""
    since = timezone.now() - timedelta(days=days)
    counts = {muscle: 0 for muscle in MUSCLES}
    sets = (
        WorkoutSet.objects.filter(
            session__user=user,
            completed=True,
        )
        .exclude(set_type="warmup")
        .filter(session__started_at__gte=since)
        .select_related("exercise")
    )
    for s in sets:
        for field in ("primary_muscles", "secondary_muscles"):
            for muscle in getattr(s.exercise, field) or []:
                key = normalize(muscle)
                if key in counts:
                    counts[key] += 1
    return counts


def volume_by_muscle(user, days=7):
    """Count completed, non-warmup sets per muscle over the last N days."""
    counts = _set_counts(user, days)
    # ponytail: thresholds are a simple heuristic, tune from real training data if needed
    return {muscle: {"sets": count, "level": _level(count)} for muscle, count in counts.items()}


def region_states(user, days=7):
    """Return {region_id: intensity} for the body-muscles chart, 0-10 scale."""
    counts = _set_counts(user, days)
    states = {}
    for muscle, count in counts.items():
        intensity = _intensity(count)
        for region in REGIONS.get(muscle, []):
            states[region] = intensity
    # ponytail: thresholds are heuristics to tune with real training data
    return states


def muscle_summary(user, muscle_key, days=7):
    """Return {direct, indirect} set counts for one canonical muscle."""
    since = timezone.now() - timedelta(days=days)
    direct = indirect = 0
    sets = (
        WorkoutSet.objects.filter(
            session__user=user,
            completed=True,
        )
        .exclude(set_type="warmup")
        .filter(session__started_at__gte=since)
        .select_related("exercise")
    )
    for s in sets:
        primary = {normalize(m) for m in s.exercise.primary_muscles or []}
        secondary = {normalize(m) for m in s.exercise.secondary_muscles or []}
        if muscle_key in primary:
            direct += 1
        if muscle_key in secondary:
            indirect += 1
    return {"direct": direct, "indirect": indirect}


def recovery_by_muscle(user):
    """Estimate recovery state per muscle from the most recent training date."""
    today = timezone.localdate()
    result = {muscle: {"days_ago": None, "state": "unknown"} for muscle in MUSCLES}
    last_dates = {}
    sets = (
        WorkoutSet.objects.filter(
            session__user=user,
            completed=True,
        )
        .exclude(set_type="warmup")
        .select_related("session", "exercise")
    )
    for s in sets:
        date = timezone.localdate(s.session.started_at)
        for field in ("primary_muscles", "secondary_muscles"):
            for muscle in getattr(s.exercise, field) or []:
                key = normalize(muscle)
                if key in result:
                    last_dates[key] = max(last_dates.get(key, date), date)
    for muscle in MUSCLES:
        last = last_dates.get(muscle)
        if last is None:
            continue
        days_ago = (today - last).days
        if days_ago == 0:
            state = "recent"
        elif days_ago == 1:
            state = "recovering"
        else:
            state = "fresh"
        result[muscle] = {"days_ago": days_ago, "state": state}
    return result
