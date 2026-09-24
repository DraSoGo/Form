"""Deterministic ingredient-based nutrition calculator."""

from core.nutrition_ref import REFERENCE, lookup

NUTRIENTS = ("kcal", "protein", "carbs", "fat", "fiber", "sugar", "sodium")


def _scale(value, weight_g, fraction=1.0):
    if value is None:
        return None
    return value * weight_g / 100.0 * fraction


def compute_ingredient(ref_entry, weight_g, fraction=1.0):
    """Return scaled nutrition for a reference entry at a given weight/fraction."""
    per = ref_entry["per_100g"]
    return {nutrient: _scale(per.get(nutrient), weight_g, fraction) for nutrient in NUTRIENTS}


def compute_meal(items, dish_name="", strategy="components", unmatched=None, completeness="complete"):
    """Compute totals and ranges from a list of FoodItem dicts.

    Each dict must contain at least 'ref_key' and 'weight_g'.
    Optional 'min_g'/'max_g' are used for the kcal range.
    Optional 'fraction_consumed' (0-1) scales nutrients.
    Optional 'custom_values' supplies hand-entered per-item nutrients that
    override the reference computation (user-added custom ingredients).
    The resolved per_100g dict is returned inside each item.
    """
    unmatched = unmatched or []
    resolved = []
    for item in items:
        weight_g = float(item.get("weight_g", 0))
        fraction = float(item.get("fraction_consumed", 1.0))
        ref_key = str(item.get("ref_key") or "")
        cv = item.get("custom_values")
        # A reference row with hand-edited cells stays a reference row:
        # custom_values override nutrients per cell (below); they do not
        # turn the whole row into a custom ingredient (that discarded the
        # row's other reference values).
        is_custom = ref_key == "custom" or item.get("custom") is True
        if is_custom:
            # User-entered custom ingredient: values are already final for
            # the given portion — scale only by the consumed fraction.
            # Fields the user left blank stay None (unknown), never zero.
            cv = cv if isinstance(cv, dict) else {}
            scaled = {}
            for nutrient in NUTRIENTS:
                raw = cv.get(nutrient)
                scaled[nutrient] = None if raw in (None, "") else round(float(raw) * fraction, 2)
            resolved.append(
                {
                    "ref_key": "custom",
                    "name_th": item.get("name_th", ""),
                    "source": "User-entered",
                    "per_100g": {k: None for k in NUTRIENTS},
                    # Echo the raw hand-entered values so a reload of the
                    # editable table shows exactly what the user typed.
                    "custom_values": {
                        k: (None if cv.get(k) in (None, "") else float(cv[k]))
                        for k in NUTRIENTS
                    },
                    "weight_g": weight_g,
                    "min_g": float(item.get("min_g", weight_g)),
                    "max_g": float(item.get("max_g", weight_g)),
                    "fraction_consumed": fraction,
                    "user_confirmed": bool(item.get("user_confirmed", False)),
                    "custom": True,
                    "computed": scaled,
                }
            )
            continue
        ref = lookup(item["ref_key"])
        if ref is None:
            raise ValueError(f"Unknown ref_key: {item['ref_key']}")
        per = ref["per_100g"]
        scaled = compute_ingredient(ref, weight_g, fraction)
        # Per-cell hand edits on a reference row override the scaled value
        # for that nutrient only (blank cell = revert to reference value).
        overrides = {}
        if cv and isinstance(cv, dict):
            overrides = {
                k: (None if cv.get(k) in (None, "") else round(float(cv[k]) * fraction, 2))
                for k in NUTRIENTS
                if cv.get(k) not in (None, "")
            }
            scaled.update(overrides)
        resolved.append(
            {
                "ref_key": item["ref_key"],
                "name_th": item.get("name_th", ref["name_th"]),
                "source": ref.get("source", ""),
                "per_100g": {k: per.get(k) for k in NUTRIENTS},
                "custom_values": overrides or None,
                "weight_g": weight_g,
                "min_g": float(item.get("min_g", weight_g)),
                "max_g": float(item.get("max_g", weight_g)),
                "fraction_consumed": fraction,
                "user_confirmed": bool(item.get("user_confirmed", False)),
                "computed": scaled,
            }
        )

    totals = {}
    unknown_fields = []
    for nutrient in NUTRIENTS:
        values = [
            ing["computed"][nutrient]
            for ing in resolved
            if ing["computed"][nutrient] is not None
        ]
        # ponytail: sum the known values; a substantial (>=20g) ingredient
        # lacking the nutrient is flagged in unknown_fields instead of
        # voiding the whole total. Voiding let one blank custom row zero
        # out every NOT NULL column on the entry (data loss).
        if values:
            totals[nutrient] = round(sum(values), 2)
            if any(
                ing["computed"][nutrient] is None and ing["weight_g"] >= 20
                for ing in resolved
            ):
                unknown_fields.append(nutrient)
        else:
            totals[nutrient] = None
            unknown_fields.append(nutrient)

    def _kcal_at(ing, grams):
        # Custom rows carry hand-entered kcal for the portion (already
        # fraction-scaled); reference rows scale per_100g by min/max grams.
        if ing.get("custom"):
            return ing["computed"]["kcal"] or 0
        return (
            (ing["per_100g"]["kcal"] or 0)
            * grams
            / 100.0
            * ing.get("fraction_consumed", 1.0)
        )

    kcal_min = round(sum(_kcal_at(ing, ing["min_g"]) for ing in resolved), 2)
    kcal_max = round(sum(_kcal_at(ing, ing["max_g"]) for ing in resolved), 2)

    # Completeness: major unmatched items make the meal incomplete.
    complete = completeness != "incomplete" and not any(
        u.get("estimated_share") == "major" for u in unmatched
    )

    return {
        "dish_name": dish_name,
        "strategy": strategy,
        "complete": complete,
        "ingredients": resolved,
        "unmatched": unmatched,
        "totals": totals,
        "range_kcal": [kcal_min, kcal_max],
        "unknown_fields": unknown_fields,
    }


def validate_meal(computed):
    """Return a list of issue strings. Empty list means acceptable.

    Completeness problems (major unmatched components) do NOT appear here:
    they are recorded on the computed result, and an incomplete meal is
    still saved — flagged for the user — rather than rejected.
    """
    issues = []
    ingredients = computed.get("ingredients", [])
    totals = computed.get("totals", {})

    # Negative values.
    for ing in ingredients:
        for nutrient, value in ing["computed"].items():
            if value is not None and value < 0:
                issues.append(f"negative {nutrient} in {ing['ref_key']}")
        if ing["weight_g"] < 0 or ing["weight_g"] > 2000:
            issues.append(f"implausible weight {ing['weight_g']}g for {ing['ref_key']}")

    # Duplicated ref_key + weight entries.
    seen = set()
    for ing in ingredients:
        key = (ing["ref_key"], ing["weight_g"])
        if key in seen:
            issues.append(f"duplicate {ing['ref_key']} {ing['weight_g']}g")
        seen.add(key)

    # Macro consistency.
    kcal = totals.get("kcal")
    protein = totals.get("protein")
    carbs = totals.get("carbs")
    fat = totals.get("fat")
    if kcal is not None and protein is not None and carbs is not None and fat is not None:
        estimated = 4 * protein + 4 * carbs + 9 * fat
        if estimated > 0 and abs(kcal - estimated) / estimated > 0.25:
            issues.append("kcal inconsistent with macros")

    # Density plausibility.
    total_weight = sum(ing["weight_g"] for ing in ingredients)
    if total_weight > 0 and kcal is not None and kcal / total_weight > 9:
        issues.append("kcal density exceeds 9 per gram")

    # Sugar > carbs.
    sugar = totals.get("sugar")
    if sugar is not None and carbs is not None and sugar > carbs:
        issues.append("sugar exceeds carbs")

    # Total kcal cap.
    if kcal is not None and kcal > 5000:
        issues.append("total kcal exceeds 5000")

    # All-zero guard: any substantial item should produce >0 kcal.
    if kcal is not None and kcal <= 0 and any(ing["weight_g"] > 50 for ing in ingredients):
        issues.append("zero kcal despite substantial ingredients")

    return issues
