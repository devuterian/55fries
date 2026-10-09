import unittest

from scripts.normalize_mcp_refresh import (
    DEFECT_VARIANT, UNKNOWN_CAPACITY_VARIANT, body_capacity, capacity, choose_variant, classify, comparable,
    mentions_defect, model_matches, normalize, normalize_v2,
)


class ModelMatchTest(unittest.TestCase):
    def test_rejects_nearby_models(self):
        cases = [
            ("iPhone 16", "아이폰 16pro 256GB"),
            ("iPhone 17", "아이폰 17e 256GB"),
            ("Canon R1", "캐논 R10 바디"),
            ("Nikon Zf", "니콘 Zfc 바디"),
            ("Sony FX3", "소니 FX30 바디"),
            ("Fujifilm X-E5", "후지 X-E4 바디, X-E5 문의"),
            ("Fujifilm X100VI", "후지 X100V, X100VI 문의"),
            ("Sony a7C II", "소니 a7c 실버 블랙 바디 민트급 a7c2 a7cii"),
        ]
        for model, title in cases:
            with self.subTest(model=model, title=title):
                self.assertFalse(model_matches(model, title))

    def test_accepts_exact_models(self):
        self.assertTrue(model_matches("iPhone 16 Pro", "아이폰16 프로 256GB"))
        self.assertTrue(model_matches("Canon R10", "캐논 R10 바디"))
        self.assertTrue(model_matches("Sony a7 III", "소니 A7M3 바디"))
        self.assertTrue(model_matches("Sony a7C II", "소니 A7C II 바디"))

    def test_separates_new_nearby_models(self):
        cases = [
            ("iPhone 14 Pro", "아이폰 14 프로맥스 256GB"),
            ("Ricoh GR IV", "리코 GR III HDF 카메라"),
            ("Ricoh GR IV", "리코 GR IV HDF 카메라"),
            ("GoPro MISSION 1", "고프로 Mission 1 Pro"),
            ("MacBook Pro M4 Pro", "맥북프로 16 M4 Max"),
        ]
        for model, title in cases:
            with self.subTest(model=model, title=title):
                self.assertFalse(model_matches(model, title))

    def test_separates_added_phone_models(self):
        rejected = [
            ("iPhone 16", "아이폰 16e 128GB"),
            ("iPhone 15", "아이폰 15 프로 256GB"),
            ("iPhone 15", "아이폰15 플러스 128"),
            ("iPhone 13", "아이폰 13 미니 128GB"),
            ("iPhone 13 Pro", "아이폰 13 프로맥스 256GB"),
            ("Galaxy Z Flip7", "갤럭시 Z 플립7 FE 256GB"),
            ("Galaxy S24", "갤럭시 S24 울트라 256GB"),
            ("Galaxy S24", "갤럭시 S24 FE 256GB"),
            ("Galaxy S23", "갤럭시 S23+ 256GB"),
        ]
        for model, title in rejected:
            with self.subTest(model=model, title=title):
                self.assertFalse(model_matches(model, title))
        accepted = [
            ("iPhone 16e", "아이폰 16e 128GB"),
            ("iPhone 17 Pro Max", "아이폰17 프로맥스 512GB"),
            ("Galaxy Z Flip7 FE", "갤럭시 Z 플립7 FE 256GB"),
            ("Galaxy S24+", "갤럭시 S24 플러스 256GB"),
            ("Galaxy S23 FE", "갤럭시 S23 FE 256GB"),
        ]
        for model, title in accepted:
            with self.subTest(model=model, title=title):
                self.assertTrue(model_matches(model, title))

    def test_two_terabyte_capacity(self):
        self.assertEqual(choose_variant("iPhone 17 Pro Max", ["256GB", "512GB", "1TB", "2TB"], "아이폰 17 프로맥스 2TB"), "2TB")

    def test_assigns_new_variants(self):
        self.assertEqual(
            choose_variant("DJI Mini 5 Pro", ["스탠다드", "플라이 모어"], "DJI 미니5 프로 플라이 모어 콤보"),
            "플라이 모어",
        )
        self.assertEqual(
            choose_variant("MacBook Air M4", ["13인치", "15인치"], "맥북에어 M4 15인치"),
            "15인치",
        )
        self.assertEqual(
            choose_variant(
                "Apple Watch Series 10",
                ["42mm GPS", "42mm Cellular", "46mm GPS", "46mm Cellular"],
                "애플워치10 46mm 셀룰러",
            ),
            "46mm Cellular",
        )

    def test_rtx_laptop_stays_excluded(self):
        product = {"brand": "NVIDIA", "model": "RTX 4080", "variant": "16GB"}
        self.assertFalse(comparable(product, "RTX 4080 노트북", None, 2_000_000))

    def test_rtx_laptop_in_description_stays_excluded(self):
        product = {"brand": "NVIDIA", "model": "RTX 4090", "variant": "24GB"}
        self.assertFalse(comparable(product, "RTX 4090", "게이밍 노트북에서 분리한 GPU", 3_000_000))

    def test_rtx_memory_mismatch_stays_excluded(self):
        product = {"brand": "NVIDIA", "model": "RTX 4090", "variant": "24GB"}
        self.assertFalse(comparable(product, "RTX 4090 20GB 내용 필독", None, 3_000_000))

    def test_single_capacity_and_no_burn_in_wording(self):
        self.assertEqual(choose_variant("Galaxy S22", ["256GB"], "갤럭시 S22 무잔상"), "256GB")
        product = {"brand": "Samsung", "model": "Galaxy S22", "variant": "256GB"}
        self.assertTrue(comparable(product, "갤럭시 S22 256GB 무잔상", None, 280_000))

    def test_terabyte_capacity_before_korean_text(self):
        self.assertEqual(capacity("갤럭시 S23 울트라 1TB 그린"), "1TB")
        self.assertEqual(capacity("갤럭시 S23 울트라 1테라 S급"), "1TB")

    def test_active_sold_overlap_is_recorded_and_not_imported_as_sold(self):
        item = {
            "sequence": 123,
            "title": "캐논 R10 바디",
            "price_krw": 800_000,
            "listing_url": "https://web.joongna.com/product/123",
            "sorted_at": "2026-09-20 12:00:00",
        }
        raw = {
            "run_id": "overlap-fixture",
            "fetched_at": "2026-09-20T12:00:00+09:00",
            "queries": [{
                "model": "Canon R10",
                "joongna": {
                    "fetched_at": "2026-09-20T12:00:00+09:00",
                    "available_listings": [item],
                    "sold_price_history": {"listings": [item]},
                },
                "bunjang": {"listings": []},
            }],
        }
        catalog = {"products": [{"brand": "Canon", "model": "Canon R10", "variant": "바디"}]}
        result = normalize(raw, catalog)
        self.assertEqual([listing["state"] for listing in result["listings"]], ["active"])
        self.assertEqual(result["quality_issues"][0]["overlap_count"], 1)

    def test_non_overlapping_sold_listing_remains_available_for_history(self):
        sold = {
            "sequence": 456,
            "title": "캐논 R10 바디",
            "price_krw": 700_000,
            "listing_url": "https://web.joongna.com/product/456",
            "sorted_at": "2026-09-10 12:00:00",
        }
        raw = {
            "run_id": "sold-fixture",
            "fetched_at": "2026-09-20T12:00:00+09:00",
            "queries": [{
                "model": "Canon R10",
                "joongna": {
                    "fetched_at": "2026-09-20T12:00:00+09:00",
                    "available_listings": [],
                    "sold_price_history": {"listings": [sold]},
                },
                "bunjang": {"listings": []},
            }],
        }
        catalog = {"products": [{"brand": "Canon", "model": "Canon R10", "variant": "바디"}]}
        result = normalize(raw, catalog)
        self.assertEqual([listing["state"] for listing in result["listings"]], ["sold"])
        self.assertEqual(result["quality_issues"], [])


if __name__ == "__main__":
    unittest.main()


class NormalizeV2Test(unittest.TestCase):
    CATALOG = {"products": [{"brand": "Sony", "model": "Sony a7 IV", "variant": "바디"}]}

    def raw(self, joongna_items, bunjang_items):
        def response(items):
            return {"page_observed_at": "2026-10-09T06:00:00.000Z", "listings": items}

        return {
            "schema_version": 2, "run_id": "v2-fixture", "fetched_at": "2026-10-09T06:00:00.000Z",
            "queries": [{
                "model": "Sony a7 IV",
                "joongna": {"response": response(joongna_items)},
                "bunjang": {"response": response(bunjang_items)},
            }],
        }

    def item(self, marketplace, listing_id, title, price, seller, **extra):
        return {
            "marketplace": marketplace, "listing_id": listing_id, "title": title, "price_krw": price,
            "status": "on_sale", "seller_id": seller, "description": None,
            "listing_url": f"https://example.test/{marketplace}/{listing_id}", **extra,
        }

    def test_seller_safety_comes_from_joongna_evidence_only(self):
        evidence = {
            "status": "available", "checked_at": "2026-10-09T06:00:01.000Z",
            "source_metrics": {"safeTradeCount": 3},
            "safe_trade_count": {"value": 3, "status": "available", "source_field": "safeTradeCount"},
        }
        bunjang_evidence = {
            "status": "available", "source_metrics": {"salesCount": 52},
            "safe_trade_count": {"value": None, "status": "unavailable", "reason": "equivalence_unverified"},
        }
        raw = self.raw(
            [self.item("joongna", "1", "소니 a7m4 바디", 1_700_000, "10", source_dates={"sortDate": "2026-10-09 14:00:00"}, seller_evidence=evidence)],
            [self.item("bunjang", "2", "소니 A7M4 바디", 1_650_000, "20", updated_at="2026-10-08T01:00:00Z", seller_evidence=bunjang_evidence)],
        )
        result = normalize_v2(raw, self.CATALOG)
        listings = {item["marketplace"]: item for item in result["listings"]}
        self.assertEqual(listings["joongna"]["updated_at"], "2026-10-09T14:00:00+09:00")
        checks = {item["marketplace"]: item for item in result["seller_safety_checks"]}
        self.assertEqual(checks["joongna"]["verification_status"], "verified")
        self.assertEqual(checks["joongna"]["safe_trade_count"], 3)
        self.assertEqual(checks["bunjang"]["verification_status"], "unavailable")
        self.assertIsNone(checks["bunjang"]["safe_trade_count"])

    def test_v2_drops_non_active_accessories_and_cheap_listings(self):
        raw = self.raw(
            [
                self.item("joongna", "3", "소니 a7m4 바디", 2_000, "10", source_dates={"sortDate": "2026-10-09 14:00:00"}),
                self.item("joongna", "4", "소니 a7m4 케이스", 50_000, "10", source_dates={"sortDate": "2026-10-09 14:00:00"}),
                {**self.item("joongna", "5", "소니 a7m4 바디", 1_700_000, "10"), "status": "sold"},
            ],
            [],
        )
        self.assertEqual(normalize_v2(raw, self.CATALOG)["listings"], [])


def phone_products(model, variants):
    return [{"brand": "Apple", "model": model, "variant": value} for value in variants]


class TierTest(unittest.TestCase):
    def setUp(self):
        capacities = ["128GB", "256GB", "512GB", UNKNOWN_CAPACITY_VARIANT, DEFECT_VARIANT]
        self.products = {
            "iPhone 16": phone_products("iPhone 16", capacities),
            "iPhone 16 Pro": phone_products("iPhone 16 Pro", capacities[:3] + ["1TB"] + capacities[3:]),
            "iPhone 16 Pro Max": phone_products("iPhone 16 Pro Max", ["256GB", "512GB", "1TB"] + capacities[3:]),
        }

    def variant(self, title, description=None, price=700_000, query="iPhone 16"):
        product = classify(query, title, description, price, self.products)
        return product and (product["model"], product["variant"])

    def test_other_model_moves_instead_of_dropping(self):
        self.assertEqual(self.variant("아이폰 16 프로 256GB"), ("iPhone 16 Pro", "256GB"))
        self.assertEqual(self.variant("아이폰16 프맥 512"), ("iPhone 16 Pro Max", "512GB"))
        self.assertEqual(self.variant("아이폰 16 프로맥스 1테라"), ("iPhone 16 Pro Max", "1TB"))

    def test_defect_goes_to_its_own_tier(self):
        self.assertEqual(self.variant("아이폰 16 액정 깨짐 256GB"), ("iPhone 16", DEFECT_VARIANT))
        self.assertEqual(self.variant("아이폰 16 부품용", price=120_000), ("iPhone 16", DEFECT_VARIANT))
        self.assertIsNone(self.variant("아이폰 16 부품용", price=90_000))
        for body in ("뒷판 파손 있어요", "미세 잔상이 있어 저렴하게 판매 합니다", "번인현상이 있네요", "망원 카메라에 실금이 있습니다"):
            with self.subTest(body=body):
                self.assertEqual(self.variant("아이폰 16 256GB", body), ("iPhone 16", DEFECT_VARIANT))

    def test_denied_defect_in_body_is_not_defect(self):
        for body in (
            "고장 없음", "파손 없이 깨끗합니다", "무잔상 무번인", "잔상X 번인X", "노파손", "침수 이력 없습니다",
            "무상 A/S는 액정파손/외관훼손 제외", "※ 파손 / 침수 / 사용자과실 및", "분실 도난 침수폰 일절 취급하지 않습니다",
            "B급 : 액정 약 잔상 있거나 기스 있고", "택배거래시 파손면책 동의하시면 가능", "✅특S급 : [ 찍힘❌ / 잔상❌ ]",
        ):
            with self.subTest(body=body):
                self.assertFalse(mentions_defect(body, body=True))
                self.assertEqual(self.variant("아이폰 16 256GB", body), ("iPhone 16", "256GB"))

    def test_capacity_from_body_or_unknown(self):
        self.assertEqual(self.variant("아이폰 16 블랙 S급", "용량은 256GB 입니다"), ("iPhone 16", "256GB"))
        self.assertEqual(self.variant("아이폰 16 블랙 S급", "128GB 256GB 512GB 재고 있음"), ("iPhone 16", UNKNOWN_CAPACITY_VARIANT))
        self.assertEqual(self.variant("아이폰 16 블랙 S급"), ("iPhone 16", UNKNOWN_CAPACITY_VARIANT))
        self.assertIsNone(body_capacity("가격 256,000원"))

    def test_non_listing_words_still_dropped(self):
        self.assertIsNone(self.variant("아이폰 16 삽니다"))
        self.assertIsNone(self.variant("아이폰 16 케이스 일괄"))
