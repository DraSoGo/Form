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
    The resolved per_100g dict is returned inside each item.
    """
    unmatched = unmatched or []
    resolved = []
    for item in items:
        ref = lookup(item["ref_key"])
        if ref is None:
            raise ValueError(f"Unknown ref_key: {item['ref_key']}")
        per = ref["per_100g"]
        weight_g = float(item.get("weight_g", 0))
        fraction = float(item.get("fraction_consumed", 1.0))
        scaled = compute_ingredient(ref, weight_g, fraction)
        resolved.append(
            {
                "ref_key": item["ref_key"],
                "name_th": item.get("name_th", ref["name_th"]),
                "source": ref.get("source", ""),
                "per_100g": {k: per.get(k) for k in NUTRIENTS},
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
        # A nutrient is unknown if any ingredient >= 20g lacks it.
        missing = any(
            ing["computed"][nutrient] is None and ing["weight_g"] >= 20
            for ing in resolved
        )
        if missing or not values:
            totals[nutrient] = None
            if missing:
                unknown_fields.append(nutrient)
        else:
            totals[nutrient] = round(sum(values), 2)

    kcal_min = round(
        sum(
            (ing["per_100g"]["kcal"] or 0) * ing["min_g"] / 100.0 * ing.get("fraction_consumed", 1.0)
            for ing in resolved
        ),
        2,
    )
    kcal_max = round(
        sum(
            (ing["per_100g"]["kcal"] or 0) * ing["max_g"] / 100.0 * ing.get("fraction_consumed", 1.0)
            for ing in resolved
        ),
        2,
    )

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
