import unittest

from scripts.refresh_sold_averages import (
    _normalize,
    alert_max_price,
    comparable_prices,
    model_excludes,
)


class SoldAverageTest(unittest.TestCase):
    def test_alert_price_is_15_percent_below_and_rounded_down(self):
        self.assertEqual(alert_max_price(580_850), 490_000)
        self.assertLessEqual(alert_max_price(580_850), 580_850 * 0.85)

    def test_comparable_prices_remove_floor_and_large_outlier(self):
        self.assertEqual(
            comparable_prices([50_000, 400_000, 500_000, 600_000, 2_000_000], 100_000),
            [400_000, 500_000, 600_000],
        )


if __name__ == "__main__":
    unittest.main()


class ExcludeKeywordTests(unittest.TestCase):
    def test_base_models_exclude_variants_and_accessories(self):
        s25 = model_excludes("Galaxy S25")
        self.assertIsNotNone(s25)
        for term in ("울트라", "플러스", "엣지", "fe", "케이스"):
            self.assertIn(term, s25)
        i16 = model_excludes("iPhone 16")
        for term in ("프로", "플러스", "맥스", "16e"):
            self.assertIn(term, i16)

    def test_iphone_pro_excludes_pro_max(self):
        self.assertEqual(model_excludes("iPhone 16 Pro")[:3], ["맥스", "max", "프로맥스"])

    def test_non_variant_models_keep_chart(self):
        self.assertIsNone(model_excludes("Sony a7 IV"))
        self.assertIsNone(model_excludes("Apple Watch Series 10"))

    def test_normalize_strips_space_and_lowercases(self):
        self.assertEqual(_normalize(" 갤럭시 S25 "), "갤럭시s25")
