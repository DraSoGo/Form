"""Deterministic ingredient-based nutrition calculator."""

from core.nutrition_ref import REFERENCE, lookup

NUTRIENTS = ("kcal", "protein", "carbs", "fat", "fiber", "sugar", "sodium")


def _scale(value, weight_g):
    if value is None:
        return None
    return value * weight_g / 100.0


def compute_ingredient(ref_entry, weight_g):
    """Return scaled nutrition for a reference entry at a given weight."""
    per = ref_entry["per_100g"]
    return {nutrient: _scale(per.get(nutrient), weight_g) for nutrient in NUTRIENTS}


def compute_meal(ingredients):
    """Compute totals and ranges from a list of ingredient dicts.

    Each dict must contain at least 'ref_key' and 'weight_g'.
    Optional 'min_g'/'max_g' are used for the kcal range.
    The resolved per_100g dict is returned inside each ingredient.
    """
    resolved = []
    for item in ingredients:
        ref = lookup(item["ref_key"])
        if ref is None:
            raise ValueError(f"Unknown ref_key: {item['ref_key']}")
        per = ref["per_100g"]
        weight_g = float(item.get("weight_g", 0))
        scaled = compute_ingredient(ref, weight_g)
        resolved.append(
            {
                "ref_key": item["ref_key"],
                "name_th": item.get("name_th", ref["name_th"]),
                "source": ref.get("source", ""),
                "per_100g": {k: per.get(k) for k in NUTRIENTS},
                "weight_g": weight_g,
                "min_g": float(item.get("min_g", weight_g)),
                "max_g": float(item.get("max_g", weight_g)),
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
            (ing["per_100g"]["kcal"] or 0) * ing["min_g"] / 100.0
            for ing in resolved
        ),
        2,
    )
    kcal_max = round(
        sum(
            (ing["per_100g"]["kcal"] or 0) * ing["max_g"] / 100.0
            for ing in resolved
        ),
        2,
    )

    return {
        "ingredients": resolved,
        "totals": totals,
        "range_kcal": [kcal_min, kcal_max],
        "unknown_fields": unknown_fields,
    }


def validate_meal(computed):
    """Return a list of issue strings. Empty list means acceptable."""
    issues = []
    ingredients = computed.get("ingredients", [])
    totals = computed.get("totals", {})

    # Negative values.
    for ing in ingredients:
        for nutrient, value in ing["computed"].items():
            if value is not None and value < 0:
                issues.append(f"negative {nutrient} in {ing['ref_key']}")
        if ing["weight_g"] < 0 or ing["weight_g"] > 1500:
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
    if (
        sugar is not None
        and carbs is not None
        and sugar > carbs
    ):
        issues.append("sugar exceeds carbs")

    # Total kcal cap.
    if kcal is not None and kcal > 5000:
        issues.append("total kcal exceeds 5000")

    return issues
