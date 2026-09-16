import io, uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import *

NUTRIENTS = ["calories", "protein", "carbs", "fat", "fiber", "sugar", "sodium"]


def active_target(user):
    return NutritionTarget.objects.filter(user=user).first()


def active_plan(user):
    return WorkoutPlan.objects.filter(user=user).first()


def target_payload(target):
    return {k: float(getattr(target, k)) for k in NUTRIENTS[:5]} if target else {}


def plan_payload(plan):
    return (
        {
            k: getattr(plan, k)
            for k in ["name", "schedule_type", "schedule", "exercises"]
        }
        if plan
        else {}
    )


def _version(user, model, expected):
    get_user_model().objects.select_for_update().get(pk=user.pk)
    last = model.objects.filter(user=user).first()
    version = last.version if last else 0
    try:
        stale = expected is not None and int(expected) != version
    except (ValueError, TypeError):
        raise ValidationError("Invalid version. Reload before applying changes.")
    if stale:
        raise ValidationError("This version is stale. Reload before applying changes.")
    return version + 1


@transaction.atomic
def create_target(user, data, reason="", expected_version=None):
    version = _version(user, NutritionTarget, expected_version)
    if set(data) - set(NUTRIENTS[:5]):
        raise ValidationError("Unknown target fields")
    obj = NutritionTarget(user=user, version=version, reason=reason, **data)
    obj.full_clean()
    obj.save()
    return obj


@transaction.atomic
def create_plan(user, data, reason="", expected_version=None):
    version = _version(user, WorkoutPlan, expected_version)
    if set(data) - {"name", "schedule_type", "schedule", "exercises"}:
        raise ValidationError("Unknown plan fields")
    schedule = data.get("schedule")
    exercises = data.get("exercises")
    if data.get("schedule_type") == "fixed":
        if not isinstance(schedule, dict) or any(
            k not in map(str, range(7)) or not isinstance(v, str)
            for k, v in schedule.items()
        ):
            raise ValidationError("Fixed schedule must map weekdays 0–6 to day names.")
    elif data.get("schedule_type") == "rotation":
        if (
            not isinstance(schedule, list)
            or not schedule
            or len(schedule) > 31
            or any(not isinstance(x, str) for x in schedule)
        ):
            raise ValidationError("Rotation must be a list of day names.")
    else:
        raise ValidationError("Choose fixed or rotation.")
    if not isinstance(exercises, list) or len(exercises) > 100:
        raise ValidationError("Invalid exercise list")
    for item in exercises:
        if not isinstance(item, dict):
            raise ValidationError("Invalid exercise")
        try:
            exercise = Exercise.objects.get(id=item.get("exercise"), user=user)
        except (Exercise.DoesNotExist, ValueError, ValidationError):
            raise ValidationError("Unknown exercise reference")
        if exercise.archived:
            raise ValidationError("Archived exercises cannot be added to a new plan")
        common = {"exercise", "day", "order", "notes"}
        if not isinstance(item.get("day", ""), str) or not 1 <= len(item.get("day", "")) <= 80:
            raise ValidationError("Invalid workout day")
        if not isinstance(item.get("notes", ""), str) or len(item.get("notes", "")) > 2000:
            raise ValidationError("Invalid exercise notes")
        if exercise.activity_type == "cardio":
            if set(item) - (common | {"minutes"}):
                raise ValidationError("Cardio plans use duration only")
            minutes = item.get("minutes")
            if type(minutes) is not int or not 1 <= minutes <= 1440:
                raise ValidationError("Invalid cardio duration")
            ranges = [("order", 0, 100)]
        else:
            if set(item) - (common | {"sets", "rep_min", "rep_max", "rest", "rir", "rpe"}):
                raise ValidationError("Invalid strength prescription")
            ranges = [
            ("sets", 1, 30),
            ("rep_min", 1, 100),
            ("rep_max", 1, 100),
            ("rest", 0, 3600),
            ("order", 0, 100),
            ]
        for key, low, high in ranges:
            value = item.get(
                key,
                {"sets": 3, "rep_min": 8, "rep_max": 12, "rest": 90, "order": 1}[key],
            )
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not low <= value <= high
            ):
                raise ValidationError("Invalid " + key)
        if exercise.activity_type == "strength" and item.get("rep_min", 8) > item.get("rep_max", 12):
            raise ValidationError("Rep minimum exceeds maximum")
        for key in (["rir", "rpe"] if exercise.activity_type == "strength" else []):
            if item.get(key) is not None and (
                not isinstance(item[key], (float, int)) or not 0 <= item[key] <= 10
            ):
                raise ValidationError("Invalid " + key)
    obj = WorkoutPlan(user=user, version=version, reason=reason, **data)
    obj.full_clean()
    obj.save()
    return obj


def nutrition_totals(user, start, end):
    values = FoodEntry.objects.filter(
        user=user, recorded_at__gte=start, recorded_at__lt=end
    ).aggregate(**{x: Sum(x) for x in NUTRIENTS})
    return {k: float(v or 0) for k, v in values.items()}


def weekly_volume(user):
    result = {}
    for item in (
        WorkoutSet.objects.filter(
            session__user=user,
            session__started_at__gte=timezone.now() - timedelta(days=7),
            completed=True,
        )
        .exclude(set_type="warmup")
        .select_related("exercise")
    ):
        for field, label in [
            ("primary_muscles", "direct"),
            ("secondary_muscles", "indirect"),
        ]:
            for muscle in getattr(item.exercise, field):
                result.setdefault(muscle, {"direct": 0, "indirect": 0})[label] += 1
    return result


@transaction.atomic
def calculate_target(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    body = BodyMeasurement.objects.filter(user=user, weight__isnull=False).first()
    if not body or not profile.height or not profile.age or not profile.sex:
        raise ValidationError(
            "Enter age, sex, height in Settings and add a weight measurement first."
        )
    if profile.age < 18:
        raise ValidationError(
            "Automatic calorie targets are available for adults. Set targets with qualified guidance for younger users."
        )
    bmr = (
        10 * float(body.weight)
        + 6.25 * float(profile.height)
        - 5 * profile.age
        + (5 if profile.sex == "male" else -161)
    )
    calories = max(
        1200,
        round(
            bmr * float(profile.activity)
            + {"lose": -300, "gain": 200, "maintain": 0}[profile.goal]
        ),
    )
    protein = round(float(body.weight) * 1.6)
    fat = round(calories * 0.25 / 9)
    BodyMeasurement.objects.create(
        user=user,
        source="calculated",
        bmr=round(bmr),
        bmi=round(float(body.weight) / (float(profile.height) / 100) ** 2, 2),
    )
    return create_target(
        user,
        dict(
            calories=calories,
            protein=protein,
            fat=fat,
            carbs=max(0, round((calories - 4 * protein - 9 * fat) / 4)),
            fiber=round(calories / 1000 * 14),
        ),
        reason="Mifflin–St Jeor estimate; activity multiplier and moderate goal adjustment.",
    )


def save_image(upload):
    if upload.size > 10 * 1024 * 1024:
        raise ValidationError("Image must be at most 10 MB.")
    try:
        raw = upload.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValidationError("Image too large")
        with Image.open(io.BytesIO(raw)) as img:
            if (
                img.format not in ["JPEG", "PNG", "WEBP"]
                or img.width * img.height > 24000000
            ):
                raise ValidationError("Use JPEG, PNG or WebP under 24 megapixels.")
            if (
                upload.content_type
                != {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}[
                    img.format
                ]
            ):
                raise ValidationError("Image MIME type does not match its contents.")
            img.load()
            img = img.convert("RGB")
            img.thumbnail((2048, 2048))
            name = uuid.uuid4().hex + ".jpg"
            Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
            img.save(Path(settings.MEDIA_ROOT) / name, "JPEG", quality=88)
            return name
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ValidationError("Invalid image file.")


def delete_image(entry, status="deleted"):
    if entry.image:
        path = Path(settings.MEDIA_ROOT) / Path(entry.image).name
        path.unlink(missing_ok=True)
    entry.image = ""
    entry.image_status = status
    entry.save(update_fields=["image", "image_status"])


def retain_images():
    count = 0
    for profile in Profile.objects.exclude(image_retention_days=0):
        for entry in FoodEntry.objects.filter(
            user=profile.user,
            recorded_at__lt=timezone.now()
            - timedelta(days=profile.image_retention_days),
        ).exclude(image=""):
            delete_image(entry, "expired")
            count += 1
    return count


@transaction.atomic
def start_session(user, plan=None, name="Workout", copy_last=False):
    session = WorkoutSession.objects.create(user=user, plan=plan, name=name)
    last = (
        WorkoutSession.objects.filter(user=user, name=name)
        .exclude(pk=session.pk)
        .first()
        if copy_last
        else None
    )
    if last:
        for item in last.sets.all():
            item.pk = uuid.uuid4()
            item.session = session
            item.completed = False
            item.save(force_insert=True)
        for item in last.cardio.all():
            item.pk = uuid.uuid4()
            item.session = session
            item.completed = False
            item.save(force_insert=True)
    elif plan:
        for item in plan.exercises:
            if item.get("day", name) != name:
                continue
            exercise = Exercise.objects.get(pk=item["exercise"], user=user)
            # The versioned prescription shape owns historical behavior even if
            # the library entry is edited later.
            if "minutes" in item:
                WorkoutCardio.objects.create(
                    session=session,
                    exercise=exercise,
                    order=item.get("order", 1) * 100,
                    minutes=item["minutes"],
                    notes=item.get("notes", ""),
                )
                continue
            for i in range(item.get("sets", 3)):
                WorkoutSet.objects.create(
                    session=session,
                    exercise_id=item["exercise"],
                    order=item.get("order", 1) * 100 + i,
                    reps=item.get("rep_min", 8),
                    rir=item.get("rir"),
                    rpe=item.get("rpe"),
                    rest_seconds=item.get("rest", 90),
                    notes=item.get("notes", ""),
                )
    return session
