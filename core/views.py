import json
from datetime import timedelta, datetime, time
from pathlib import Path
from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Avg, Max, Sum
from django.http import FileResponse, HttpResponse, JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import *
from .forms import *
from .services import *
from .archive import export_archive, validate_archive, import_archive, export_csv
from .muscles import muscle_summary, region_states


def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unhealthy"}, status=503)
    return JsonResponse({"status": "ok"})


def dashboard(request):
    today = timezone.localdate()
    start = timezone.make_aware(datetime.combine(today, time.min))
    end = start + timedelta(days=1)
    target = active_target(request.user)
    totals = nutrition_totals(request.user, start, end)
    plan = active_plan(request.user)
    scheduled = ""
    if plan:
        if plan.schedule_type == "fixed":
            scheduled = plan.schedule.get(str(today.weekday()), "Rest")
        else:
            completed = WorkoutSession.objects.filter(
                user=request.user, plan=plan, finished_at__isnull=False
            ).count()
            scheduled = plan.schedule[completed % len(plan.schedule)]
    bars = []
    for name in ["calories", "protein", "carbs", "fat", "fiber", "sugar", "sodium"]:
        goal = float(getattr(target, name)) if target and getattr(target, name, None) else 0
        bars.append(
            {
                "name": name,
                "value": round(totals[name]),
                "target": round(goal),
                "percent": min(100, round(totals[name] / goal * 100)) if goal else 0,
            }
        )
    # Exercise list for today's scheduled day (the same derivation the
    # workouts view uses for plan cards).
    today_exercises = []
    if plan and scheduled and scheduled != "Rest":
        exercise_ids = {
            item.get("exercise") for item in plan.exercises if item.get("exercise")
        }
        names_by_pk = {
            str(ex.pk): ex.name
            for ex in Exercise.objects.filter(user=request.user, pk__in=exercise_ids)
        }
        single_day = len(set(plan.schedule.values() if plan.schedule_type == "fixed" else plan.schedule) - {"Rest"}) <= 1
        for item in plan.exercises:
            day = item.get("day", scheduled if single_day else None)
            if day != scheduled:
                continue
            name = names_by_pk.get(str(item.get("exercise")))
            if not name:
                continue
            if "minutes" in item:
                today_exercises.append({"name": name, "detail": f"{item['minutes']} min"})
            else:
                today_exercises.append(
                    {"name": name, "detail": f"{item.get('sets', 3)} × {item.get('rep_min', 8)}–{item.get('rep_max', 12)}"}
                )
        today_exercises = today_exercises[:6]
    muscle_groups = [
        {"key": muscle, **muscle_summary(request.user, muscle)}
        for muscle in ["chest", "back", "shoulders", "biceps", "triceps", "abs", "glutes", "quads", "hamstrings", "calves"]
    ]
    return render(
        request,
        "core/dashboard.html",
        {
            "today": today,
            "bars": bars,
            "body": BodyMeasurement.objects.filter(
                user=request.user, weight__isnull=False
            ).first(),
            "sleep": SleepEntry.objects.filter(user=request.user).first(),
            "scheduled": scheduled,
            "plan": plan,
            "today_exercises": today_exercises,
            "muscle_regions": region_states(request.user, 7),
            "muscle_groups": muscle_groups,
            "foods": FoodEntry.objects.filter(
                user=request.user, recorded_at__gte=start
            )[:5],
            "sessions": WorkoutSession.objects.filter(user=request.user)[:3],
        },
    )


def body(request):
    use_advanced = request.POST.get("advanced") == "1"
    form_class = AdvancedBodyForm if use_advanced else BodyForm
    form = form_class(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.user = request.user
        item.save()
        if "coaching" in settings.INSTALLED_APPS:
            from coaching.services import on_body_saved

            on_body_saved(request.user)
        messages.success(
            request, "Measurement saved. Previous readings remain in your history."
        )
        return redirect("/body/")
    advanced_form = AdvancedBodyForm()
    latest = BodyMeasurement.objects.filter(user=request.user).order_by("-recorded_at").first()
    latest_summary = {
        "weight": latest.weight,
        "body_fat": latest.body_fat,
        "recorded_at": latest.recorded_at,
        "source": latest.source,
    } if latest else {}
    return render(
        request,
        "core/body.html",
        {
            "form": form,
            "advanced_form": advanced_form,
            "advanced_fields": [
                advanced_form[f] for f in ("muscle", "visceral_fat", "body_age", "bmr", "bmi")
            ],
            "latest": latest_summary,
            "measurements": BodyMeasurement.objects.filter(user=request.user)[:100],
            "sleep": SleepEntry.objects.filter(user=request.user)[:14],
            "steps": StepEntry.objects.filter(user=request.user)[:30],
        },
    )


def generic_edit(request, kind, pk=None):
    mapping = {
        "body": (BodyMeasurement, AdvancedBodyForm, "Body measurement"),
        "sleep": (SleepEntry, SleepForm, "Sleep"),
        "cardio": (CardioEntry, CardioForm, "Cardio"),
        "step": (StepEntry, StepForm, "Steps"),
        "equipment": (Equipment, EquipmentForm, "Equipment"),
        "exercise": (Exercise, ExerciseForm, "Exercise"),
        "library": (FoodLibrary, LibraryForm, "Saved food"),
    }
    if kind not in mapping:
        raise Http404
    model, form_class, title = mapping[kind]
    instance = get_object_or_404(model, pk=pk, user=request.user) if pk else None
    form_kwargs = {"instance": instance}
    if kind == "exercise":
        form_kwargs["user"] = request.user
    form = form_class(request.POST or None, **form_kwargs)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        if kind == "exercise":
            # Empty strings from the comma-list field must not look like
            # real aliases when checking for conflicts.
            new_names = {
                obj.name.casefold(),
                *[str(x).casefold() for x in obj.aliases if str(x).strip()],
            }
            conflict = None
            for other in Exercise.objects.filter(user=request.user).exclude(pk=obj.pk):
                existing = {
                    other.name.casefold(),
                    *[str(a).casefold() for a in other.aliases if str(a).strip()],
                }
                overlap = new_names & existing
                if overlap:
                    conflict = (other, overlap)
                    break
            if conflict:
                form.add_error(
                    "name",
                    f"This name or alias already belongs to the exercise "
                    f"\"{conflict[0].name}\". Use that entry instead.",
                )
            elif not all(
                isinstance(getattr(obj, f), list)
                and all(isinstance(x, str) and len(x) < 80 for x in getattr(obj, f))
                for f in ["aliases", "primary_muscles", "secondary_muscles"]
            ):
                form.add_error(
                    None, "Muscle groups and aliases must be JSON lists of short names."
                )
            else:
                obj.save()
                if "coaching" in settings.INSTALLED_APPS:
                    from coaching.services import enqueue_exercise
                    enqueue_exercise(request.user, obj)
                return redirect("/workouts/")
        else:
            obj.save()
            return redirect(
                "/settings/"
                if kind == "equipment"
                else "/nutrition/"
                if kind == "library"
                else "/body/"
            )
    template = "core/exercise_form.html" if kind == "exercise" else "core/form.html"
    return render(
        request,
        template,
        {"form": form, "title": ("Edit " if pk else "Add ") + title,
         "delete_kind": kind if pk and kind not in ("equipment", "exercise") else None,
         "object": instance},
    )


@require_POST
def equipment_delete(request, pk):
    get_object_or_404(Equipment, pk=pk, user=request.user).delete()
    return redirect("/settings/")


@require_POST
def record_delete(request, kind, pk):
    mapping = {
        "body": (BodyMeasurement, "/body/"),
        "sleep": (SleepEntry, "/body/"),
        "step": (StepEntry, "/body/"),
        "cardio": (CardioEntry, "/workouts/"),
        "food": (FoodEntry, "/nutrition/"),
        "library": (FoodLibrary, "/nutrition/"),
        "template": (MealTemplate, "/nutrition/"),
        "session": (WorkoutSession, "/workouts/"),
    }
    if kind == "set":
        item = get_object_or_404(WorkoutSet, pk=pk, session__user=request.user)
        redirect_to = "/workouts/session/" + str(item.session_id) + "/"
    elif kind == "workout-cardio":
        item = get_object_or_404(WorkoutCardio, pk=pk, session__user=request.user)
        redirect_to = "/workouts/session/" + str(item.session_id) + "/"
    elif kind in mapping:
        model, redirect_to = mapping[kind]
        item = get_object_or_404(model, pk=pk, user=request.user)
    else:
        raise Http404
    if isinstance(item, FoodEntry) and item.image:
        delete_image(item)
    item.delete()
    return redirect(redirect_to)


def nutrition(request):
    today = timezone.localdate()
    date_param = request.GET.get("date", "today")
    if date_param == "today":
        selected_date = today
    else:
        try:
            selected_date = datetime.strptime(date_param, "%Y-%m-%d").date()
        except ValueError:
            selected_date = today
    start = timezone.make_aware(datetime.combine(selected_date, time.min))
    end = start + timedelta(days=1)

    active_status = request.GET.get("status", "")
    valid_states = {
        choice[0] for choice in FoodEntry._meta.get_field("state").choices
    }
    if active_status and active_status not in valid_states:
        active_status = ""

    foods = FoodEntry.objects.filter(
        user=request.user, recorded_at__gte=start, recorded_at__lt=end
    )
    if active_status:
        foods = foods.filter(state=active_status)
    foods = foods.order_by("-recorded_at")[:100]

    return render(
        request,
        "core/nutrition.html",
        {
            "foods": foods,
            "library": FoodLibrary.objects.filter(user=request.user),
            "templates": MealTemplate.objects.filter(user=request.user),
            "totals": nutrition_totals(request.user, start, end),
            "target": active_target(request.user),
            "selected_date": selected_date,
            "active_status": active_status,
            "state_choices": FoodEntry._meta.get_field("state").choices,
        },
    )


def food_edit(request, pk=None):
    obj = get_object_or_404(FoodEntry, pk=pk, user=request.user) if pk else None
    form = FoodForm(
        request.POST or None,
        instance=obj,
        has_photo=bool(request.FILES.get("photo") or (obj and obj.image)),
    )
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        entry.user = request.user
        try:
            if request.FILES.get("photo"):
                image = save_image(request.FILES["photo"])
                if obj and obj.image:
                    delete_image(obj)
                entry.image = image
                entry.image_status = "stored"
            if pk:
                entry.state = (
                    "user_corrected" if entry.state != "confirmed" else "confirmed"
                )
            entry.save()
            if request.POST.get("save_library"):
                values = {x: getattr(entry, x) for x in ["quantity", *NUTRIENTS]}
                saved = FoodLibrary.objects.filter(
                    user=request.user, name=entry.name, quantity=entry.quantity
                ).first()
                if saved:
                    for k, v in values.items():
                        setattr(saved, k, v)
                    saved.save()
                else:
                    FoodLibrary.objects.create(
                        user=request.user, name=entry.name, **values
                    )
            messages.success(request, "Food saved. Your daily totals are updated.")
            return redirect(
                "/nutrition/" + str(entry.pk) + "/"
                if request.FILES.get("photo")
                else "/nutrition/"
            )
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request,
        "core/food_form.html",
        {"form": form, "entry": obj, "title": "Correct food" if pk else "Log food"},
    )


@require_POST
def library_use(request, pk):
    item = get_object_or_404(FoodLibrary, pk=pk, user=request.user)
    FoodEntry.objects.create(
        user=request.user,
        state="confirmed",
        **{x: getattr(item, x) for x in ["name", "quantity", *NUTRIENTS]},
    )
    return redirect("/nutrition/")


@require_POST
def template_save(request):
    ids = request.POST.getlist("food_ids")
    items = []
    for food in FoodEntry.objects.filter(user=request.user, pk__in=ids):
        items.append(
            {
                x: str(getattr(food, x)) if getattr(food, x) is not None else None
                for x in ["name", "quantity", *NUTRIENTS]
            }
        )
    name = request.POST.get("name", "").strip()[:160]
    if items and name:
        MealTemplate.objects.create(user=request.user, name=name, items=items)
        messages.success(request, "Meal template saved.")
    else:
        messages.error(request, "Choose food entries and name your template.")
    return redirect("/nutrition/")


@require_POST
def template_use(request, pk):
    template = get_object_or_404(MealTemplate, pk=pk, user=request.user)
    with transaction.atomic():
        for values in template.items:
            obj = FoodEntry(user=request.user, state="confirmed", **values)
            obj.full_clean()
            obj.save()
    return redirect("/nutrition/")


def photo(request, pk):
    entry = get_object_or_404(FoodEntry, pk=pk, user=request.user)
    if not entry.image:
        raise Http404
    path = Path(settings.MEDIA_ROOT) / Path(entry.image).name
    try:
        response = FileResponse(path.open("rb"), content_type="image/jpeg")
    except FileNotFoundError:
        raise Http404
    response["Cache-Control"] = "private, no-store"
    response["Content-Disposition"] = "inline"
    return response


@require_POST
def photo_delete(request, pk):
    delete_image(get_object_or_404(FoodEntry, pk=pk, user=request.user))
    return redirect("/nutrition/")


def targets(request):
    current = active_target(request.user)
    initial = target_payload(current)
    # Optional targets prefill only when set; None keeps the field empty.
    for name in ("sugar", "sodium"):
        if current and getattr(current, name, None) is not None:
            initial[name] = getattr(current, name)
    form = TargetForm(request.POST or None, initial=initial)
    if request.method == "POST":
        try:
            if request.POST.get("action") == "calculate":
                calculate_target(request.user)
                return redirect("/targets/")
            if form.is_valid():
                create_target(
                    request.user,
                    form.cleaned_data,
                    reason="Manually edited",
                    expected_version=request.POST.get("version", "0"),
                )
                return redirect("/targets/")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request,
        "core/targets.html",
        {
            "form": form,
            "target": current,
            "history": NutritionTarget.objects.filter(user=request.user)[:20],
        },
    )


def workouts(request):
    plan = active_plan(request.user)
    plan_days = []
    if plan:
        if plan.schedule_type == "fixed":
            day_names = []
            seen = set()
            for weekday in range(7):
                name = plan.schedule.get(str(weekday))
                if name and name not in seen:
                    day_names.append(name)
                    seen.add(name)
        else:
            day_names = list(plan.schedule)
        today = timezone.localdate()
        if plan.schedule_type == "fixed":
            scheduled = plan.schedule.get(str(today.weekday()), "Rest")
        else:
            completed = WorkoutSession.objects.filter(
                user=request.user, plan=plan, finished_at__isnull=False
            ).count()
            scheduled = plan.schedule[completed % len(plan.schedule)]
        exercise_ids = {
            item.get("exercise") for item in plan.exercises if item.get("exercise")
        }
        names_by_pk = {
            str(ex.pk): ex.name
            for ex in Exercise.objects.filter(user=request.user, pk__in=exercise_ids)
        }
        single_day = len(day_names) == 1
        for day_name in day_names:
            if single_day:
                items = [
                    item for item in plan.exercises
                    if item.get("day", day_name) == day_name
                ]
            else:
                items = [
                    item for item in plan.exercises
                    if item.get("day") == day_name
                ]
            total_sets = 0
            duration = 0
            first_exercises = []
            for item in items:
                is_cardio = "minutes" in item
                if is_cardio:
                    total_sets += 1
                    sets = None
                    duration += item.get("minutes", 20)
                else:
                    sets = item.get("sets", 3)
                    total_sets += sets
                    duration += sets * 3
                if len(first_exercises) < 3:
                    name = names_by_pk.get(str(item.get("exercise")))
                    if name:
                        first_exercises.append({"name": name, "sets": sets})
            # ponytail: duration is a crude per-exercise estimate; refine with logged times
            plan_days.append({
                "name": day_name,
                "sets": total_sets,
                "duration": round(duration / 5) * 5,
                "exercise_count": len(items),
                "first_exercises": first_exercises,
                "more": max(0, len(items) - 3),
                "today": day_name == scheduled,
            })
    # Muscle map: per training day via ?day=, defaulting to the last 7 days.
    training_days = list(
        WorkoutSession.objects.filter(user=request.user)
        .exclude(name="Rest")
        .values_list("started_at", flat=True)
        .order_by("-started_at")[:14]
    )
    day_options = sorted(
        {timezone.localtime(s).date() for s in training_days}, reverse=True
    )[:10]
    selected_day = None
    day_param = request.GET.get("day", "")
    try:
        parsed = datetime.strptime(day_param, "%Y-%m-%d").date() if day_param else None
        if parsed in day_options:
            selected_day = parsed
    except ValueError:
        selected_day = None
    muscle_groups = [
        {
            "key": muscle,
            **muscle_summary(request.user, muscle, on_date=selected_day),
        }
        for muscle in ["chest", "back", "shoulders", "biceps", "triceps", "abs", "glutes", "quads", "hamstrings", "calves"]
    ]
    return render(
        request,
        "core/workouts.html",
        {
            "plan": plan,
            "plan_days": plan_days,
            "plans": WorkoutPlan.objects.filter(user=request.user)[:10],
            "sessions": WorkoutSession.objects.filter(user=request.user)[:30],
            "exercises": Exercise.objects.filter(user=request.user, archived=False),
            "archived_exercises": Exercise.objects.filter(user=request.user, archived=True),
            "legacy_cardio": CardioEntry.objects.filter(user=request.user)[:30],
            "volume": weekly_volume(request.user),
            "muscle_regions": region_states(request.user, 7, on_date=selected_day),
            "muscle_groups": muscle_groups,
            "training_day_options": day_options,
            "selected_training_day": selected_day,
        },
    )


def plan_edit(request):
    current = active_plan(request.user)
    form = PlanForm(request.POST or None, initial=plan_payload(current))
    if request.method == "POST" and form.is_valid():
        try:
            create_plan(
                request.user,
                form.cleaned_data,
                reason="Manual plan edit",
                expected_version=request.POST.get("version", "0"),
            )
            return redirect("/workouts/")
        except ValidationError as exc:
            form.add_error(None, exc)
    return render(
        request,
        "core/plan.html",
        {
            "form": form,
            "plan": current,
            "exercises": Exercise.objects.filter(user=request.user, archived=False),
            "plan_data": plan_payload(current),
        },
    )


def plan_day(request, day_name):
    """Per-day plan page: view, add, and remove exercises for one workout day."""
    plan = active_plan(request.user)
    if not plan:
        raise Http404

    if plan.schedule_type == "fixed":
        valid_days = []
        seen = set()
        for weekday in range(7):
            name = plan.schedule.get(str(weekday))
            if name and name != "Rest" and name not in seen:
                valid_days.append(name)
                seen.add(name)
    else:
        valid_days = [name for name in plan.schedule if name != "Rest"]

    if day_name not in valid_days:
        raise Http404

    today = timezone.localdate()
    if plan.schedule_type == "fixed":
        scheduled = plan.schedule.get(str(today.weekday()), "Rest")
    else:
        completed = WorkoutSession.objects.filter(
            user=request.user, plan=plan, finished_at__isnull=False
        ).count()
        scheduled = plan.schedule[completed % len(plan.schedule)]
    is_today = day_name == scheduled

    single_day = len(valid_days) == 1
    if single_day:
        items = [
            (i, item) for i, item in enumerate(plan.exercises)
            if item.get("day", day_name) == day_name
        ]
    else:
        items = [
            (i, item) for i, item in enumerate(plan.exercises)
            if item.get("day") == day_name
        ]

    exercise_ids = {str(item.get("exercise")) for _, item in items if item.get("exercise")}
    exercises_by_pk = {
        str(ex.pk): ex
        for ex in Exercise.objects.filter(user=request.user, pk__in=exercise_ids)
    }

    day_exercises = []
    for index, item in sorted(items, key=lambda x: (x[1].get("order", 1), x[0])):
        pk = str(item.get("exercise")) if item.get("exercise") else None
        exercise = exercises_by_pk.get(pk) if pk else None
        day_exercises.append(
            {
                "index": index,
                "name": exercise.name if exercise else None,
                "exercise_pk": pk,
                "activity_type": exercise.activity_type if exercise else None,
                "sets": item.get("sets"),
                "rep_min": item.get("rep_min"),
                "rep_max": item.get("rep_max"),
                "rest": item.get("rest"),
                "rir": item.get("rir"),
                "rpe": item.get("rpe"),
                "minutes": item.get("minutes"),
                "notes": item.get("notes", ""),
                "missing": exercise is None and pk is not None,
            }
        )

    form_errors = ""
    if request.method == "POST":
        action = request.POST.get("action")
        exercises = list(plan.exercises)
        try:
            if action == "add":
                exercise_pk = request.POST.get("exercise")
                exercise = Exercise.objects.get(pk=exercise_pk, user=request.user)
                if exercise.archived:
                    raise ValidationError("Archived exercises cannot be added to a new plan")

                day_orders = [
                    item.get("order", 1)
                    for item in exercises
                    if item.get("day") == day_name
                ]
                order = max(day_orders) + 1 if day_orders else 1
                notes = request.POST.get("notes", "")

                if exercise.activity_type == "cardio":
                    minutes = int(request.POST.get("minutes", 20))
                    new_item = {
                        "exercise": str(exercise.pk),
                        "day": day_name,
                        "order": order,
                        "minutes": minutes,
                        "notes": notes,
                    }
                else:
                    sets = int(request.POST.get("sets", 3))
                    rep_min = int(request.POST.get("rep_min", 8))
                    rep_max = int(request.POST.get("rep_max", 12))
                    rest = int(request.POST.get("rest", 90))
                    new_item = {
                        "exercise": str(exercise.pk),
                        "day": day_name,
                        "order": order,
                        "sets": sets,
                        "rep_min": rep_min,
                        "rep_max": rep_max,
                        "rest": rest,
                        "notes": notes,
                    }
                    rir = request.POST.get("rir")
                    rpe = request.POST.get("rpe")
                    if rir:
                        new_item["rir"] = float(rir)
                    if rpe:
                        new_item["rpe"] = float(rpe)

                exercises.append(new_item)
                create_plan(
                    request.user,
                    {
                        "name": plan.name,
                        "schedule_type": plan.schedule_type,
                        "schedule": plan.schedule,
                        "exercises": exercises,
                    },
                    reason=f"Added to {day_name}",
                    expected_version=plan.version,
                )
                return redirect(f"/workouts/day/{day_name}/")

            if action == "remove":
                index = int(request.POST.get("index", ""))
                if not (0 <= index < len(exercises)):
                    raise ValidationError("Invalid exercise index")
                exercises.pop(index)
                create_plan(
                    request.user,
                    {
                        "name": plan.name,
                        "schedule_type": plan.schedule_type,
                        "schedule": plan.schedule,
                        "exercises": exercises,
                    },
                    reason=f"Removed from {day_name}",
                    expected_version=plan.version,
                )
                return redirect(f"/workouts/day/{day_name}/")

            form_errors = "Unknown action."
        except (Exercise.DoesNotExist, ValueError, ValidationError) as exc:
            form_errors = str(exc)

    return render(
        request,
        "core/day_detail.html",
        {
            "day_name": day_name,
            "is_today": is_today,
            "day_exercises": day_exercises,
            "library": Exercise.objects.filter(user=request.user, archived=False).order_by("name"),
            "plan": plan,
            "form_errors": form_errors,
        },
    )


@require_POST
def session_start(request):
    plan = active_plan(request.user)
    name = request.POST.get("name", "Workout").strip()[:120] or "Workout"
    if name == "Rest":
        messages.info(request, "Rest day recorded by advancing the rotation.")
        session = WorkoutSession.objects.create(
            user=request.user, plan=plan, name="Rest", finished_at=timezone.now()
        )
    else:
        session = start_session(
            request.user, plan, name, request.POST.get("copy_last") == "1"
        )
    return redirect("/workouts/session/" + str(session.pk) + "/")


def session_detail(request, pk):
    session = get_object_or_404(WorkoutSession, pk=pk, user=request.user)
    form = SetForm(request.POST or None if request.POST.get("activity") != "cardio" else None)
    cardio_form = CardioLogForm(request.POST or None if request.POST.get("activity") == "cardio" else None)
    form.fields["exercise"].queryset = Exercise.objects.filter(user=request.user, archived=False, activity_type="strength")
    cardio_form.fields["exercise"].queryset = Exercise.objects.filter(user=request.user, archived=False, activity_type="cardio")
    if request.method == "POST":
        if request.POST.get("action") == "finish":
            session.finished_at = timezone.now()
            session.notes = request.POST.get("notes", "")[:4000]
            session.save()
            return redirect("/workouts/")
        if request.POST.get("activity") == "cardio" and cardio_form.is_valid():
            obj = cardio_form.save(commit=False)
            obj.session = session
            obj.save()
            return redirect(request.path)
        if request.POST.get("activity") != "cardio" and form.is_valid():
            obj = form.save(commit=False)
            obj.session = session
            obj.save()
            return redirect(request.path)
    last = WorkoutSession.objects.filter(
        user=request.user, name=session.name, started_at__lt=session.started_at
    ).first()
    # Pre-fill order with the next number after the current last set.
    next_order = (session.sets.aggregate(m=Max("order"))["m"] or 0) + 1
    form.fields["order"].initial = next_order
    cardio_form.fields["order"].initial = (
        session.cardio.aggregate(m=Max("order"))["m"] or 0
    ) + 1
    return render(
        request,
        "core/session.html",
        {
            "session": session,
            "sets": session.sets.select_related("exercise"),
            "cardio": session.cardio.select_related("exercise"),
            "form": form,
            "cardio_form": cardio_form,
            "last": last,
            "previous": last.sets.select_related("exercise") if last else [],
        },
    )


def set_edit(request, pk):
    item = get_object_or_404(WorkoutSet, pk=pk, session__user=request.user)
    form = SetForm(request.POST or None, instance=item)
    form.fields["exercise"].queryset = Exercise.objects.filter(user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("/workouts/session/" + str(item.session_id) + "/")
    return render(
        request,
        "core/form.html",
        {"form": form, "title": "Edit set · " + item.exercise.name},
    )


def cardio_edit(request, pk):
    item = get_object_or_404(WorkoutCardio, pk=pk, session__user=request.user)
    form = CardioLogForm(request.POST or None, instance=item)
    form.fields["exercise"].queryset = Exercise.objects.filter(user=request.user, activity_type="cardio")
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("/workouts/session/" + str(item.session_id) + "/")
    return render(request, "core/form.html", {"form": form, "title": "Edit cardio · " + item.exercise.name})


@require_POST
def set_complete(request, pk):
    item = get_object_or_404(WorkoutSet, pk=pk, session__user=request.user)
    item.completed = not item.completed
    item.save(update_fields=["completed"])
    return redirect(
        "/workouts/session/" + str(item.session_id) + "/?rest=" + str(item.rest_seconds)
    )


@require_POST
def cardio_complete(request, pk):
    item = get_object_or_404(WorkoutCardio, pk=pk, session__user=request.user)
    item.completed = not item.completed
    item.save(update_fields=["completed"])
    return redirect("/workouts/session/" + str(item.session_id) + "/")


@require_POST
def exercise_archive(request, pk):
    item = get_object_or_404(Exercise, pk=pk, user=request.user)
    item.archived = True
    item.save(update_fields=["archived"])
    return redirect("/workouts/")


def trends(request):
    try:
        days = int(request.GET.get("days", 30))
    except ValueError:
        days = 30
    if days not in [7, 14, 30]:
        days = 30
    start = timezone.now() - timedelta(days=days)
    groups = {}
    for entry in BodyMeasurement.objects.filter(
        user=request.user, recorded_at__gte=start
    ).order_by("recorded_at"):
        for metric in ["weight", "body_fat", "muscle"]:
            value = getattr(entry, metric)
            if value is not None:
                groups.setdefault(
                    metric + " · " + entry.get_source_display(), []
                ).append(
                    {
                        "date": timezone.localtime(entry.recorded_at).strftime("%d %b"),
                        "value": float(value),
                    }
                )
    today = timezone.localdate()
    daily = []
    for offset in reversed(range(days)):
        date = today - timedelta(days=offset)
        day_start = timezone.make_aware(datetime.combine(date, time.min))
        values = nutrition_totals(
            request.user, day_start, day_start + timedelta(days=1)
        )
        daily.append({"date": date.strftime("%d %b"), **values})
    # Only days with logged food become chart points; unlogged days would
    # otherwise draw misleading zeros across the whole range.
    logged = [d for d in daily if d["calories"] > 0]
    groups["Calories"] = [{"date": d["date"], "value": d["calories"]} for d in logged]
    groups["Protein"] = [{"date": d["date"], "value": d["protein"]} for d in logged]
    groups["Sleep"] = [
        {"date": s.date.strftime("%d %b"), "value": float(s.hours)}
        for s in SleepEntry.objects.filter(
            user=request.user, date__gte=start.date()
        ).order_by("date")
    ]
    performance = []
    for exercise in Exercise.objects.filter(user=request.user):
        sets = (
            WorkoutSet.objects.filter(
                session__user=request.user,
                exercise=exercise,
                completed=True,
                session__started_at__gte=start,
            )
            .exclude(set_type="warmup")
            .select_related("session")
            .order_by("session__started_at")
        )
        entries = [
            {
                "date": s.session.started_at.strftime("%d %b"),
                "weight": s.weight,
                "reps": s.reps,
                "rir": s.rir,
                "rpe": s.rpe,
            }
            for s in sets
        ]
        if entries:
            performance.append(
                {
                    "name": exercise.name,
                    "entries": entries,
                    "pr": max(s["weight"] for s in entries),
                }
            )
    # Summary cards
    workout_count = WorkoutSession.objects.filter(
        user=request.user, started_at__gte=start
    ).count()
    workout_sub = (
        f"{round(workout_count / days * 7, 1)} per week"
        if workout_count else "No sessions in this period"
    )

    logged_days = [d for d in daily if d["calories"] > 0]
    if logged_days:
        avg_calories = int(round(sum(d["calories"] for d in logged_days) / len(logged_days)))
        calories_value = f"{avg_calories} kcal"
        calories_sub = f"{len(logged_days)} of {days} days logged"
    else:
        calories_value = "—"
        calories_sub = "No food logged"

    sleep_points = groups.get("Sleep", [])
    if sleep_points:
        avg_sleep = round(sum(p["value"] for p in sleep_points) / len(sleep_points), 1)
        sleep_value = f"{avg_sleep} h"
        sleep_sub = f"{len(sleep_points)} nights recorded"
    else:
        sleep_value = "—"
        sleep_sub = "0 nights recorded"

    weigh_ins = list(
        BodyMeasurement.objects.filter(
            user=request.user, recorded_at__gte=start, weight__isnull=False
        ).order_by("recorded_at")
    )
    if len(weigh_ins) >= 2:
        change = float(weigh_ins[-1].weight) - float(weigh_ins[0].weight)
        if change > 0:
            weight_value = f"+{change:.1f} kg"
        elif change < 0:
            weight_value = f"{change:.1f} kg"
        else:
            weight_value = "0.0 kg"
        weight_sub = f"{len(weigh_ins)} weigh-ins"
    else:
        weight_value = "—"
        weight_sub = "Add weigh-ins to see change"

    summaries = [
        {"label": "Workouts", "value": workout_count, "sub": workout_sub},
        {"label": "Avg calories", "value": calories_value, "sub": calories_sub},
        {"label": "Avg sleep", "value": sleep_value, "sub": sleep_sub},
        {"label": "Weight change", "value": weight_value, "sub": weight_sub},
    ]

    return render(
        request,
        "core/trends.html",
        {
            "days": days,
            "charts": groups,
            "performance": performance,
            "volume": weekly_volume(request.user),
            "summaries": summaries,
        },
    )


def settings_view(request):
    profile = Profile.objects.filter(user=request.user).first() or Profile(
        user=request.user
    )
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Settings saved.")
        return redirect("/settings/")
    return render(
        request,
        "core/settings.html",
        {"form": form, "equipment": Equipment.objects.filter(user=request.user)},
    )


def password_change(request):
    form = PasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Password changed.")
        return redirect("/settings/")
    return render(request, "core/form.html", {"form": form, "title": "Change password"})


@require_POST
def logout_view(request):
    logout(request)
    return redirect("/login/")


def export_view(request, domain):
    if domain == "json":
        response = JsonResponse(export_archive(request.user))
        filename = "fitness-archive.json"
    elif domain in ["body", "nutrition", "workout"]:
        response = HttpResponse(
            export_csv(request.user, domain), content_type="text/csv; charset=utf-8"
        )
        filename = "fitness-" + domain + ".csv"
    else:
        raise Http404
    response["Content-Disposition"] = 'attachment; filename="' + filename + '"'
    response["Cache-Control"] = "no-store"
    return response


def import_view(request):
    error = ""
    preview = None
    if request.method == "POST":
        try:
            if request.POST.get("action") == "commit":
                payload = request.session.pop("import_preview", None)
                if payload is None:
                    raise ValidationError("Preview the archive first.")
                count = import_archive(
                    payload,
                    request.user,
                    keep_profile=request.session.pop("import_keep_profile", False),
                )
                messages.success(request, f"Imported {count} records.")
                return redirect("/settings/")
            upload = request.FILES.get("archive")
            if not upload or upload.size > 5 * 1024 * 1024:
                raise ValidationError("Choose a JSON archive under 5 MB.")
            raw = upload.read(5 * 1024 * 1024 + 1)
            if len(raw) > 5 * 1024 * 1024:
                raise ValidationError("Archive too large.")
            payload = json.loads(raw)
            keep_profile = request.POST.get("keep_profile") == "1"
            objects = validate_archive(payload, request.user, keep_profile=keep_profile)
            request.session["import_preview"] = payload
            request.session["import_keep_profile"] = keep_profile
            preview = {}
            if len(objects) < len(payload["records"]):
                preview["Profile kept unchanged"] = len(payload["records"]) - len(
                    objects
                )
            for obj in objects:
                preview[obj._meta.verbose_name] = (
                    preview.get(obj._meta.verbose_name, 0) + 1
                )
        except (ValidationError, ValueError, TypeError) as exc:
            error = str(exc)
    return render(
        request,
        "core/import.html",
        {
            "error": error,
            "preview": preview,
            "has_profile": Profile.objects.filter(user=request.user).exists(),
        },
    )


def manifest(request):
    return JsonResponse(
        {
            "name": "Form · Fitness & Nutrition",
            "short_name": "Form",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#101613",
            "theme_color": "#18211b",
            "icons": [
                {
                    "src": "/static/core/icon-192.png",
                    "sizes": "192x192",
                    "type": "image/png",
                },
                {
                    "src": "/static/core/icon-512.png",
                    "sizes": "512x512",
                    "type": "image/png",
                    "purpose": "any maskable",
                },
            ],
        }
    )


def service_worker(request):
    response = HttpResponse(
        (Path(__file__).parent / "static/core/sw.js").read_text(),
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
