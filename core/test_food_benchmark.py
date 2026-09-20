"""Benchmark for ingredient-level backend nutrition estimates.

These tests use curated plausible ranges (not lab data) and mock V3-style
responses representing good model behaviour. Accuracy is approximately
verified only: a real result inside the band with all major components
resolved and completeness='complete' is considered passing.
"""

from django.test import SimpleTestCase

from core.nutrition_calc import compute_meal


def _v3(dish_name, items, unmatched=None, strategy="components"):
    return compute_meal(
        items,
        dish_name=dish_name,
        strategy=strategy,
        unmatched=unmatched or [],
        completeness="complete",
    )


class FoodBenchmarkTests(SimpleTestCase):
    def _assert_in_band(self, computed, center, tolerance_percent):
        kcal = computed["totals"]["kcal"]
        low = center * (1 - tolerance_percent / 100)
        high = center * (1 + tolerance_percent / 100)
        self.assertGreaterEqual(kcal, low)
        self.assertLessEqual(kcal, high)
        self.assertTrue(computed["complete"])
        majors = [u for u in computed["unmatched"] if u.get("estimated_share") == "major"]
        self.assertEqual(majors, [])

    def test_chicken_noodle_soup(self):
        computed = _v3(
            "chicken noodle soup",
            [{"ref_key": "chicken_noodle_soup", "weight_g": 450, "min_g": 400, "max_g": 500}],
            strategy="whole_dish",
        )
        self._assert_in_band(computed, 500, 30)

    def test_basil_pork_rice_with_fried_egg(self):
        computed = _v3(
            "basil pork rice with egg",
            [
                {"ref_key": "basil_pork_rice", "weight_g": 400, "min_g": 350, "max_g": 450},
                {"ref_key": "fried_egg", "weight_g": 50, "min_g": 40, "max_g": 60},
            ],
            strategy="hybrid",
        )
        self._assert_in_band(computed, 790, 25)

    def test_fried_chicken_sticky_rice(self):
        computed = _v3(
            "fried chicken with sticky rice",
            [
                {"ref_key": "sticky_rice_cooked", "weight_g": 170, "min_g": 150, "max_g": 190},
                {"ref_key": "fried_chicken_battered", "weight_g": 180, "min_g": 160, "max_g": 200},
                {"ref_key": "fried_shallots", "weight_g": 25, "min_g": 20, "max_g": 30},
                {"ref_key": "sweet_chili_dipping_sauce", "weight_g": 30, "min_g": 25, "max_g": 35},
            ],
            strategy="components",
        )
        self._assert_in_band(computed, 750, 35)

    def test_chicken_sandwich(self):
        computed = _v3(
            "chicken sandwich",
            [{"ref_key": "chicken_sandwich", "weight_g": 220, "min_g": 200, "max_g": 240}],
            strategy="whole_dish",
        )
        self._assert_in_band(computed, 450, 30)

    def test_rice_fried_chicken(self):
        computed = _v3(
            "rice with fried chicken",
            [
                {"ref_key": "cooked_white_rice", "weight_g": 200, "min_g": 180, "max_g": 220},
                {"ref_key": "fried_chicken_battered", "weight_g": 200, "min_g": 180, "max_g": 220},
                {"ref_key": "sweet_chili_dipping_sauce", "weight_g": 30, "min_g": 20, "max_g": 40},
            ],
            strategy="components",
        )
        self._assert_in_band(computed, 800, 30)

    def test_green_curry_rice(self):
        computed = _v3(
            "green curry with rice",
            [{"ref_key": "green_curry_rice", "weight_g": 450, "min_g": 400, "max_g": 500}],
            strategy="whole_dish",
        )
        self._assert_in_band(computed, 600, 30)

    def test_hidden_sauce_pad_thai(self):
        computed = _v3(
            "pad thai",
            [{"ref_key": "pad_thai", "weight_g": 300, "min_g": 250, "max_g": 350}],
            strategy="whole_dish",
        )
        self._assert_in_band(computed, 540, 30)

    def test_ambiguous_portion_half_eaten(self):
        computed = _v3(
            "chicken noodle soup half eaten",
            [{"ref_key": "chicken_noodle_soup", "weight_g": 450, "min_g": 400, "max_g": 500, "fraction_consumed": 0.5}],
            strategy="whole_dish",
        )
        self._assert_in_band(computed, 250, 35)
