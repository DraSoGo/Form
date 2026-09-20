"""Curated local nutrition reference for ingredient-level AI food analysis.

Values are derived from USDA FoodData Central public releases and standard
Thai food-composition reference tables. They are approximations for typical
prepared/cooked portions, not live API lookups or laboratory measurements.
"""

REFERENCE = {
    "cooked_white_rice": {
        "name_en": "cooked white rice",
        "name_th": "ข้าวสวย",
        "state": "cooked",
        "per_100g": {
            "kcal": 130,
            "protein": 2.7,
            "carbs": 28.0,
            "fat": 0.3,
            "fiber": 0.4,
            "sugar": 0.1,
            "sodium": 5,
        },
        "source": "USDA FDC (approx, cooked)",
        "aliases": ["rice", "ข้าว", "ข้าวสวย"],
    },
    "sticky_rice_cooked": {
        "name_en": "sticky rice (cooked)",
        "name_th": "ข้าวเหนียวนึ่ง",
        "state": "cooked",
        "per_100g": {
            "kcal": 160,
            "protein": 4.0,
            "carbs": 36.0,
            "fat": 0.3,
            "fiber": 0.9,
            "sugar": 0.1,
            "sodium": 5,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["sticky rice", "glutinous rice", "ข้าวเหนียว"],
    },
    "chicken_breast_cooked": {
        "name_en": "chicken breast cooked (skinless)",
        "name_th": "เนื้ออกไก่สุก ไม่มีหนัง",
        "state": "cooked, skinless",
        "per_100g": {
            "kcal": 165,
            "protein": 31.0,
            "carbs": 0.0,
            "fat": 3.6,
            "fiber": 0.0,
            "sugar": 0.0,
            "sodium": 74,
        },
        "source": "USDA FDC (approx, cooked)",
        "aliases": ["chicken breast", "อกไก่"],
    },
    "fried_chicken_battered": {
        "name_en": "fried chicken with skin and batter",
        "name_th": "ไก่ทอด มีหนังแป้งทอด",
        "state": "fried, skin+batter, edible incl. skin/batter, oil already in value",
        "per_100g": {
            "kcal": 290,
            "protein": 22.0,
            "carbs": 12.0,
            "fat": 19.0,
            "fiber": 0.8,
            "sugar": 0.3,
            "sodium": 600,
        },
        "source": "USDA FDC (approx, fried)",
        "aliases": ["fried chicken", "ไก่ทอด"],
    },
    "chicken_skin_fried": {
        "name_en": "fried chicken skin",
        "name_th": "หนังไก่ทอด",
        "state": "fried skin",
        "per_100g": {
            "kcal": 450,
            "protein": 20.0,
            "carbs": 8.0,
            "fat": 38.0,
            "fiber": 0.0,
            "sugar": 0.0,
            "sodium": 650,
        },
        "source": "USDA FDC (approx, fried)",
        "aliases": ["chicken skin", "หนังไก่"],
    },
    "pork_minced_cooked_stirfry": {
        "name_en": "stir-fried minced pork (~20% fat)",
        "name_th": "หมูสับผัด",
        "state": "cooked stir-fried minced pork ~20% fat",
        "per_100g": {
            "kcal": 250,
            "protein": 20.0,
            "carbs": 3.0,
            "fat": 18.0,
            "fiber": 0.0,
            "sugar": 0.0,
            "sodium": 380,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["minced pork", "pork", "หมูสับ", "หมู"],
    },
    "century_egg": {
        "name_en": "century egg (preserved duck egg)",
        "name_th": "ไข่เยี่ยวม้า",
        "state": "preserved duck egg",
        "per_100g": {
            "kcal": 130,
            "protein": 12.0,
            "carbs": 2.0,
            "fat": 9.0,
            "fiber": 0.0,
            "sugar": 0.5,
            "sodium": 700,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["preserved egg", "ไข่เยี่ยวม้า"],
    },
    "fried_egg": {
        "name_en": "fried egg",
        "name_th": "ไข่ดาวทอด",
        "state": "fried in oil",
        "per_100g": {
            "kcal": 210,
            "protein": 6.5,
            "carbs": 0.5,
            "fat": 19.0,
            "fiber": 0.0,
            "sugar": 0.2,
            "sodium": 210,
        },
        "source": "USDA FDC (approx, fried)",
        "aliases": ["fried egg", "ไข่ดาว"],
    },
    "boiled_egg": {
        "name_en": "boiled egg",
        "name_th": "ไข่ต้ม",
        "state": "boiled",
        "per_100g": {
            "kcal": 155,
            "protein": 13.0,
            "carbs": 1.1,
            "fat": 11.0,
            "fiber": 0.0,
            "sugar": 1.1,
            "sodium": 124,
        },
        "source": "USDA FDC (approx, cooked)",
        "aliases": ["boiled egg", "ไข่ต้ม"],
    },
    "sausage_thai": {
        "name_en": "Thai-style pork sausage (cooked)",
        "name_th": "ไส้กรอก",
        "state": "Thai-style pork sausage, cooked",
        "per_100g": {
            "kcal": 300,
            "protein": 13.0,
            "carbs": 12.0,
            "fat": 24.0,
            "fiber": 0.0,
            "sugar": 3.0,
            "sodium": 900,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["sausage", "ไส้กรอก"],
    },
    "fried_shallots": {
        "name_en": "crispy fried shallots",
        "name_th": "หอมเจียวทอด",
        "state": "crispy fried shallots",
        "per_100g": {
            "kcal": 570,
            "protein": 6.0,
            "carbs": 40.0,
            "fat": 44.0,
            "fiber": 8.0,
            "sugar": 8.0,
            "sodium": 30,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["fried shallots", "หอมเจียว"],
    },
    "sweet_chili_dipping_sauce": {
        "name_en": "sweet chili dipping sauce",
        "name_th": "น้ำจิ้มแจ่ว/น้ำจิ้มไก่",
        "state": "sauce",
        "per_100g": {
            "kcal": 130,
            "protein": 1.0,
            "carbs": 30.0,
            "fat": 0.5,
            "fiber": 0.5,
            "sugar": 26.0,
            "sodium": 800,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["sweet chili sauce", "chili dipping sauce", "น้ำจิ้มไก่", "น้ำจิ้มแจ่ว"],
    },
    "soy_fish_sauce_mix": {
        "name_en": "soy/fish sauce seasoning",
        "name_th": "น้ำปลา/ซีอิ๊วปรุง",
        "state": "seasoning sauce",
        "per_100g": {
            "kcal": 60,
            "protein": 8.0,
            "carbs": 3.0,
            "fat": 0.0,
            "fiber": 0.0,
            "sugar": 2.0,
            "sodium": 6000,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["fish sauce", "soy sauce", "น้ำปลา", "ซีอิ๊ว"],
    },
    "vegetable_cucumber": {
        "name_en": "raw vegetable / cucumber",
        "name_th": "ผัก/แตงกวา",
        "state": "raw veg side",
        "per_100g": {
            "kcal": 15,
            "protein": 0.7,
            "carbs": 3.0,
            "fat": 0.1,
            "fiber": 1.0,
            "sugar": 1.5,
            "sodium": 3,
        },
        "source": "USDA FDC (approx, raw)",
        "aliases": ["cucumber", "vegetable", "แตงกวา", "ผัก"],
    },
    "basil_stirfry_veg": {
        "name_en": "stir-fried basil / holy basil",
        "name_th": "ใบโหระพาผัด",
        "state": "stir-fried basil",
        "per_100g": {
            "kcal": 40,
            "protein": 2.0,
            "carbs": 5.0,
            "fat": 1.0,
            "fiber": 2.0,
            "sugar": 0.5,
            "sodium": 200,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["basil", "holy basil", "ใบโหระพา", "กะเพรา"],
    },
    "cooking_oil": {
        "name_en": "cooking oil",
        "name_th": "น้ำมันพืช",
        "state": "added oil only when not covered by prepared entries",
        "per_100g": {
            "kcal": 884,
            "protein": 0.0,
            "carbs": 0.0,
            "fat": 100.0,
            "fiber": 0.0,
            "sugar": 0.0,
            "sodium": 0,
        },
        "source": "USDA FDC (approx)",
        "aliases": ["oil", "น้ำมัน"],
    },
    "coconut_milk_curry": {
        "name_en": "green curry with chicken (coconut milk based)",
        "name_th": "แกงเขียวหวาน",
        "state": "prepared curry with chicken",
        "per_100g": {
            "kcal": 130,
            "protein": 6.0,
            "carbs": 5.0,
            "fat": 10.0,
            "fiber": 1.0,
            "sugar": 2.0,
            "sodium": 400,
        },
        "source": "Thai FCD-style typical value",
        "aliases": ["green curry", "curry", "แกงเขียวหวาน"],
    },
    "ham": {
        "name_en": "ham",
        "name_th": "แฮม",
        "state": "cured ham",
        "per_100g": {
            "kcal": 145,
            "protein": 17.0,
            "carbs": 2.0,
            "fat": 8.0,
            "fiber": 0.0,
            "sugar": 1.0,
            "sodium": 1200,
        },
        "source": "USDA FDC (approx)",
        "aliases": ["ham", "แฮม"],
    },
}


def lookup(key):
    """Return a reference entry by exact key or alias match."""
    if key in REFERENCE:
        return REFERENCE[key]
    key_norm = str(key).strip().lower()
    for ref_key, entry in REFERENCE.items():
        if key_norm == ref_key.lower():
            return entry
        for alias in entry.get("aliases", []):
            if key_norm == alias.lower():
                return entry
    return None


def table_for_prompt():
    """Compact reference table for embedding in AI prompts."""
    lines = []
    for ref_key, entry in REFERENCE.items():
        p = entry["per_100g"]
        line = (
            f"{ref_key} | {entry['name_th']} ({entry['state']}) | "
            f"{p['kcal']}kcal P{p['protein']} C{p['carbs']} F{p['fat']} per 100g | "
            f"sodium {p['sodium']}mg"
        )
        lines.append(line)
    return "\n".join(lines)
