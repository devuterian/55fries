import unittest

from scripts.normalize_mcp_refresh import capacity, choose_variant, comparable, model_matches, normalize, normalize_v2


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
