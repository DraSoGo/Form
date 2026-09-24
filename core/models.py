import uuid
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


def number(maximum=100000):
    return models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(maximum)],
    )


def optional(maximum=100000):
    return models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(maximum)],
    )


class Record(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class Owned(Record):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        abstract = True


class Profile(Record):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    age = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(13), MaxValueValidator(120)],
    )
    sex = models.CharField(
        max_length=20,
        choices=[("male", "Male"), ("female", "Female")],
        blank=True,
        default="",
    )
    height = number(250)
    goal = models.CharField(
        max_length=20,
        choices=[
            ("maintain", "Maintain"),
            ("lose", "Lose fat"),
            ("gain", "Build muscle"),
        ],
        default="maintain",
    )
    activity = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=1.4,
        validators=[MinValueValidator(1.1), MaxValueValidator(2.4)],
    )
    timezone = models.CharField(max_length=60, default="Asia/Bangkok")
    summary_time = models.TimeField(default="21:00")
    image_retention_days = models.PositiveIntegerField(
        default=90,
        choices=[
            (30, "30 days"),
            (90, "90 days"),
            (180, "180 days"),
            (0, "Keep forever"),
        ],
    )


class BodyMeasurement(Owned):
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    source = models.CharField(
        max_length=40,
        choices=[
            (x, x.replace("_", " ").title())
            for x in ["manual", "smart_scale", "calculated", "future_external_source"]
        ],
        default="manual",
    )
    weight = optional(500)
    body_fat = optional(100)
    muscle = optional(100)
    visceral_fat = optional(100)
    body_age = optional(150)
    bmr = optional(10000)
    bmi = optional(150)
    # Tape measurements (cm) — optional, additive columns.
    waist = optional(300)
    arm = optional(300)
    thigh = optional(300)

    class Meta:
        ordering = ["-recorded_at"]


class SleepEntry(Owned):
    date = models.DateField(default=timezone.localdate, db_index=True)
    hours = number(24)
    note = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["-date"]


class CardioEntry(Owned):
    recorded_at = models.DateTimeField(default=timezone.now)
    kind = models.CharField(max_length=100)
    minutes = number(1440)
    note = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["-recorded_at"]


class StepEntry(Owned):
    date = models.DateField(default=timezone.localdate, db_index=True)
    steps = models.PositiveIntegerField(
        validators=[MaxValueValidator(200000)]
    )
    note = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="steps_user_date")
        ]


class Equipment(Owned):
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="equipment_name")
        ]

    def __str__(self):
        return self.name


class NutritionTarget(Owned):
    version = models.PositiveIntegerField()
    calories = number(10000)
    protein = number(1000)
    carbs = number(2000)
    fat = number(1000)
    fiber = number(200)
    sugar = optional(4000)
    sodium = optional(100000)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["user", "version"], name="target_version")
        ]


class Nutrients(Owned):
    name = models.CharField(max_length=160)
    quantity = models.CharField(max_length=120, blank=True)
    calories = number(20000)
    protein = number(2000)
    carbs = number(4000)
    fat = number(2000)
    fiber = number(500)
    sugar = optional(4000)
    sodium = optional(100000)

    class Meta:
        abstract = True


class FoodEntry(Nutrients):
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    note = models.TextField(blank=True, max_length=4000)
    state = models.CharField(
        max_length=30,
        choices=[
            (x, x.replace("_", " ").title())
            for x in ["manual", "ai_estimated", "user_corrected", "confirmed"]
        ],
        default="manual",
    )
    uncertainty = models.TextField(blank=True)
    image = models.CharField(max_length=250, blank=True)
    image_status = models.CharField(max_length=30, default="none")
    ai_breakdown = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-recorded_at"]


class FoodLibrary(Nutrients):
    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name + " " + self.quantity


class MealTemplate(Owned):
    name = models.CharField(max_length=160)
    items = models.JSONField(default=list)


class Exercise(Owned):
    activity_type = models.CharField(
        max_length=20,
        choices=[("strength", "Strength / weights"), ("cardio", "Cardio")],
        default="strength",
    )
    name = models.CharField(max_length=120)
    default_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Duration (minutes)",
        validators=[MinValueValidator(1), MaxValueValidator(1440)],
    )
    aliases = models.JSONField(default=list, blank=True)
    primary_muscles = models.JSONField(default=list, blank=True)
    secondary_muscles = models.JSONField(default=list, blank=True)
    equipment = models.CharField(max_length=150, blank=True)
    classification = models.CharField(
        max_length=20,
        choices=[("", "Not set"), ("compound", "Compound"), ("isolation", "Isolation")],
        default="",
        blank=True,
    )
    archived = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["user", "name"], name="exercise_name")
        ]

    def __str__(self):
        return self.name


class WorkoutPlan(Owned):
    version = models.PositiveIntegerField()
    name = models.CharField(max_length=120)
    schedule_type = models.CharField(
        max_length=20, choices=[("fixed", "Fixed calendar"), ("rotation", "Rotation")]
    )
    schedule = models.JSONField(default=list)
    exercises = models.JSONField(default=list, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["user", "version"], name="plan_version")
        ]


class WorkoutSession(Owned):
    plan = models.ForeignKey(
        WorkoutPlan, on_delete=models.PROTECT, null=True, blank=True
    )
    name = models.CharField(max_length=120)
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, max_length=4000)

    class Meta:
        ordering = ["-started_at"]


class WorkoutSet(Record):
    session = models.ForeignKey(
        WorkoutSession, on_delete=models.CASCADE, related_name="sets"
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT)
    order = models.PositiveIntegerField(default=1)
    weight = number(1000)
    reps = models.PositiveIntegerField(default=8, validators=[MaxValueValidator(1000)])
    rir = optional(10)
    rpe = optional(10)
    set_type = models.CharField(
        max_length=20,
        choices=[("warmup", "Warmup"), ("working", "Working"), ("drop", "Drop")],
        default="working",
    )
    completed = models.BooleanField(default=False)
    rest_seconds = models.PositiveIntegerField(
        default=90, validators=[MaxValueValidator(3600)]
    )
    failure = models.BooleanField(default=False)
    superset = models.CharField(max_length=30, blank=True)
    notes = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["order", "created_at"]


class WorkoutCardio(Record):
    session = models.ForeignKey(
        WorkoutSession, on_delete=models.CASCADE, related_name="cardio"
    )
    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT)
    order = models.PositiveIntegerField(default=1)
    minutes = models.PositiveIntegerField(
        default=20, validators=[MinValueValidator(1), MaxValueValidator(1440)]
    )
    completed = models.BooleanField(default=False)
    notes = models.TextField(blank=True, max_length=2000)

    class Meta:
        ordering = ["order", "created_at"]


class LoginAttempt(models.Model):
    key = models.CharField(max_length=64, unique=True)
    count = models.PositiveIntegerField(default=0)
    window = models.DateTimeField(default=timezone.now)
