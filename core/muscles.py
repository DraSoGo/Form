"""Muscle Map logic.

These helpers estimate training load and recovery state from logged sets.
They are not medical or physiological measurements.
"""

from datetime import datetime, time, timedelta

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
    "pectoralis major": "chest",
    "pectoralis minor": "chest",
    "back": "back",
    "lats": "back",
    "latissimus dorsi": "back",
    "lower back": "back",
    "traps": "back",
    "trapezius": "back",
    "erector spinae": "back",
    "spinal erectors": "back",
    "rhomboids": "back",
    "shoulders": "shoulders",
    "delts": "shoulders",
    "deltoids": "shoulders",
    "front delts": "shoulders",
    "side delts": "shoulders",
    "rear delts": "shoulders",
    "anterior deltoid": "shoulders",
    "lateral deltoid": "shoulders",
    "posterior deltoid": "shoulders",
    "anterior delt": "shoulders",
    "posterior delt": "shoulders",
    "rotator cuff": "shoulders",
    "biceps": "biceps",
    "biceps brachii": "biceps",
    "brachialis": "biceps",
    "triceps": "triceps",
    "triceps brachii": "triceps",
    "anconeus": "triceps",
    "abs": "abs",
    "core": "abs",
    "obliques": "abs",
    "abdominals": "abs",
    "rectus abdominis": "abs",
    "transverse abdominis": "abs",
    "hip flexors": "abs",
    "hip flexor": "abs",
    "glutes": "glutes",
    "gluteus maximus": "glutes",
    "gluteus medius": "glutes",
    "gluteus minimus": "glutes",
    "quads": "quads",
    "quadriceps": "quads",
    "quadriceps femoris": "quads",
    "hamstrings": "hamstrings",
    "calves": "calves",
    "gastrocnemius": "calves",
    "soleus": "calves",
    "tibialis anterior": "calves",
    # Thai names previously filled by AI on the production instance.
    "กล้ามเนื้อน่อง (แกสโทรคนีเมียส)": "calves",
    "กล้ามเนื้อน่องชั้นลึก (โซเลียส)": "calves",
    "กล้ามเนื้อน่อง (gastrocnemius)": "calves",
    "กล้ามเนื้อช่วยกดปลายเท้า": "calves",
    "กล้ามเนื้อพยุงข้อเท้า": "calves",
    "กล้ามเนื้อไตรเซ็ปส์": "triceps",
    "กล้ามเนื้อไตรเซ็ปส์ต้นแขน (triceps brachii)": "triceps",
    "กล้ามเนื้อแอนโคเนียสบริเวณข้อศอก (anconeus)": "triceps",
    "กล้ามเนื้อหน้าอก": "chest",
    "กล้ามเนื้อปีกหลัง": "back",
    "กล้ามเนื้อหลังส่วนกว้าง": "back",
    "กล้ามเนื้อหลังส่วนกว้าง (latissimus dorsi)": "back",
    "กล้ามเนื้อหลังส่วนกลาง": "back",
    "กล้ามเนื้อหลังส่วนล่าง": "back",
    "กล้ามเนื้อสี่เหลี่ยมขนมเปียกปูน": "back",
    "กล้ามเนื้อทราพีเซียส": "back",
    "กล้ามเนื้อทราพีเซียสส่วนกลางและส่วนล่าง": "back",
    "กล้ามเนื้อเดลทอยด์ด้านหลัง": "shoulders",
    "กล้ามเนื้อหัวไหล่": "shoulders",
    "กล้ามเนื้อหัวไหล่ด้านหน้า": "shoulders",
    "กล้ามเนื้อหัวไหล่ด้านหลัง": "shoulders",
    "กล้ามเนื้อไหล่": "shoulders",
    "กล้ามเนื้อหลังไหล่": "shoulders",
    "กล้ามเนื้อหมุนไหล่ออก": "shoulders",
    "กล้ามเนื้อหน้าแขน": "biceps",
    "กล้ามเนื้อต้นแขนด้านหน้า (ไบเซปส์)": "biceps",
    "กล้ามเนื้อไบเซปส์": "biceps",
    "กล้ามเนื้อแขนส่วนปลาย": "triceps",
    "กล้ามเนื้อปลายแขน": "triceps",
    "กล้ามเนื้อท่อนแขน": "triceps",
    "กล้ามเนื้อเบรเคียลิส": "biceps",
    "กล้ามเนื้อเบรคิโอเรเดียลิส": "biceps",
    "กล้ามเนื้อเบรคิโอเรเดียลิสบริเวณปลายแขน": "biceps",
    "กล้ามเนื้อหน้าท้องตรง": "abs",
    "กล้ามเนื้อหน้าท้องขวาง": "abs",
    "กล้ามเนื้อแกนกลางลำตัว": "abs",
    "กล้ามเนื้อก้น": "glutes",
    "กล้ามเนื้อก้นใหญ่": "glutes",
    "กล้ามเนื้อก้นใหญ่ส่วนบน": "glutes",
    "กล้ามเนื้อก้นกลาง": "glutes",
    "กล้ามเนื้อก้นเล็ก": "glutes",
    "กล้ามเนื้อหน้าขา (quadriceps)": "quads",
    "กล้ามเนื้อต้นขาด้านหน้า": "quads",
    "กล้ามเนื้อหุบต้นขามัดใหญ่": "quads",
    "กล้ามเนื้อต้นขาด้านหลัง": "hamstrings",
    "กล้ามเนื้อต้นขาด้านหลัง (hamstrings)": "hamstrings",
    "กล้ามเนื้อเหยียดแนวกระดูกสันหลัง": "back",
    "กล้ามเนื้อสี่เหลี่ยมคางหมู": "back",
    "กล้ามเนื้อเทนเซอร์ ฟาสเซีย ลาตา": "glutes",
    "กล้ามเนื้อพังผืดต้นขา": "quads",
    "กล้ามเนื้อปลายแขนและแรงจับ": "triceps",
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


def _set_counts(user, days=7, on_date=None):
    """Return raw completed, non-warmup set counts per canonical muscle.

    on_date limits counting to a single user-local day; days is otherwise
    a lookback window from now.
    """
    counts = {muscle: 0 for muscle in MUSCLES}
    sets = WorkoutSet.objects.filter(
        session__user=user,
        completed=True,
    ).exclude(set_type="warmup")
    if on_date is not None:
        start = timezone.make_aware(datetime.combine(on_date, time.min))
        sets = sets.filter(
            session__started_at__gte=start,
            session__started_at__lt=start + timedelta(days=1),
        )
    else:
        since = timezone.now() - timedelta(days=days)
        sets = sets.filter(session__started_at__gte=since)
    sets = sets.select_related("exercise")
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


def region_states(user, days=7, on_date=None):
    """Return {region_id: intensity} for the body-muscles chart, 0-10 scale.

    on_date visualizes a single user-local day; otherwise the last N days.
    """
    counts = _set_counts(user, days, on_date=on_date)
    states = {}
    for muscle, count in counts.items():
        intensity = _intensity(count)
        for region in REGIONS.get(muscle, []):
            states[region] = intensity
    # ponytail: thresholds are heuristics to tune with real training data
    return states


def muscle_summary(user, muscle_key, days=7, on_date=None):
    """Return {direct, indirect} set counts for one canonical muscle.

    on_date limits counting to a single user-local day.
    """
    direct = indirect = 0
    sets = WorkoutSet.objects.filter(
        session__user=user,
        completed=True,
    ).exclude(set_type="warmup")
    if on_date is not None:
        start = timezone.make_aware(datetime.combine(on_date, time.min))
        sets = sets.filter(
            session__started_at__gte=start,
            session__started_at__lt=start + timedelta(days=1),
        )
    else:
        since = timezone.now() - timedelta(days=days)
        sets = sets.filter(session__started_at__gte=since)
    sets = sets.select_related("exercise")
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
