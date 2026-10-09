import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.manage_db import build_site, compute_price_guide, connect, display_rows, ingest_payload, migrate

KST = timezone(timedelta(hours=9))


class PricingRulesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.connection = connect(Path(self.temp.name) / "test.sqlite")
        migrate(self.connection)
        self.as_of = datetime(2026, 9, 20, 12, 0, tzinfo=KST)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def listing(self, listing_id, price, age_days, seller, *, model="Test Camera", state="active", sold_age_days=None):
        stamp = self.as_of - timedelta(days=age_days)
        return {
            "marketplace": "joongna", "external_listing_id": listing_id,
            "brand": "Test", "model": model, "variant": "Body",
            "seller_external_id": seller, "seller_name": seller,
            "title": f"{model} {listing_id}",
            "listing_url": f"https://web.joongna.com/product/{listing_id}",
            "price_krw": price, "state": state,
            "listed_at": stamp.isoformat(), "updated_at": stamp.isoformat(),
            "sold_at": ((self.as_of - timedelta(days=sold_age_days)).isoformat() if sold_age_days is not None else None),
            "is_comparable": True,
        }

    def safety(self, seller, count):
        return {
            "marketplace": "joongna", "seller_external_id": seller,
            "checked_at": self.as_of.isoformat(), "verification_status": "verified",
            "safe_trade_count": count,
            "source_url": f"https://web.joongna.com/user/{seller}",
        }

    def test_25_day_cutoff_and_safe_column(self):
        payload = {
            "run_id": "fixture", "fetched_at": self.as_of.isoformat(),
            "listings": [
                self.listing("old-cheap", 50, 26, "safe-seller"),
                self.listing("zero-low", 100, 2, "zero-seller"),
                self.listing("safe-low", 120, 2, "safe-seller"),
                self.listing("sold-10", 80, 10, "safe-seller", state="sold", sold_age_days=10),
                self.listing("sold-100", 70, 100, "safe-seller", state="sold", sold_age_days=100),
                self.listing("sold-190", 60, 190, "safe-seller", state="sold", sold_age_days=190),
            ],
            "seller_safety_checks": [self.safety("zero-seller", 0), self.safety("safe-seller", 2)],
        }
        ingest_payload(self.connection, payload)
        run_id = compute_price_guide(self.connection, self.as_of.isoformat(), "test-25-day")
        row = display_rows(self.connection, run_id)[0]
        self.assertEqual(row["current"], 100)
        self.assertEqual(row["currentUrl"], "https://web.joongna.com/product/zero-low")
        self.assertEqual(row["safe"], 120)
        self.assertEqual(row["safeUrl"], "https://web.joongna.com/product/safe-low")
        self.assertEqual(row["safety"], "주의 · 안전거래 0회")
        self.assertEqual(row["low6"], 70)
        self.assertEqual(row["avg3"], 80)
        self.assertEqual(row["n3"], 1)
        with tempfile.TemporaryDirectory() as output:
            build_site(self.connection, Path(output))
            html = (Path(output) / "index.html").read_text()
            self.assertIn("판매중은 최근 25일 이내만", html)
            self.assertIn('const ASOF="2026-09-20T12:00:00+09:00"', html)
            self.assertIn("55<b>FRIES</b>", html)
            self.assertIn('id="guide"', html)
            self.assertIn("확인 필요", html)
            self.assertIn("판단 불가", html)
            self.assertIn("function judge(x)", html)
            self.assertIn("dealScore(a.x)-dealScore(b.x)", html)
            self.assertIn('aria-label="모델 검색"', html)
            self.assertNotIn("fonts.googleapis.com", html)
            self.assertNotIn("iconify", html)
            self.assertNotIn("<th>판매중-안전</th>", html)
            self.assertNotIn("priceCell('판매중-안전'", html)

    def test_unavailable_history_is_caution_but_safe_listing_remains(self):
        payload = {
            "run_id": "fixture-2", "fetched_at": self.as_of.isoformat(),
            "listings": [
                self.listing("unknown-low", 90, 1, None, model="Test Phone"),
                self.listing("verified-safe", 110, 1, "safe-seller", model="Test Phone"),
            ],
            "seller_safety_checks": [self.safety("safe-seller", 1)],
        }
        ingest_payload(self.connection, payload)
        run_id = compute_price_guide(self.connection, self.as_of.isoformat(), "test-unavailable")
        row = next(row for row in display_rows(self.connection, run_id) if row["model"] == "Test Phone")
        self.assertEqual(row["current"], 90)
        self.assertEqual(row["safety"], "주의 · 안전거래 이력 확인불가")
        self.assertEqual(row["safe"], 110)
        self.assertEqual(row["safeUrl"], "https://web.joongna.com/product/verified-safe")

    def test_reingesting_same_run_replaces_removed_observations(self):
        payload = {
            "run_id": "replace-fixture", "fetched_at": self.as_of.isoformat(),
            "listings": [self.listing("removed-on-refresh", 90, 1, None, model="Test Phone")],
            "seller_safety_checks": [],
        }
        ingest_payload(self.connection, payload)
        payload["listings"] = []
        ingest_payload(self.connection, payload)
        run_id = compute_price_guide(self.connection, self.as_of.isoformat(), "replace-fixture-price")
        row = display_rows(self.connection, run_id)[0]
        self.assertIsNone(row["current"])

    def test_earlier_day_observations_are_not_reused(self):
        earlier = self.as_of - timedelta(days=3)
        ingest_payload(
            self.connection,
            {
                "run_id": "fixture-earlier", "fetched_at": earlier.isoformat(),
                "listings": [self.listing("gone-since", 60, 3, "seller", model="Stale Phone")],
                "seller_safety_checks": [],
            },
        )
        ingest_payload(
            self.connection,
            {
                "run_id": "fixture-today", "fetched_at": self.as_of.isoformat(),
                "listings": [self.listing("still-here", 90, 1, "seller", model="Stale Phone")],
                "seller_safety_checks": [],
            },
        )
        run_id = compute_price_guide(self.connection, self.as_of.isoformat(), "test-same-day")
        row = next(row for row in display_rows(self.connection, run_id) if row["model"] == "Stale Phone")
        self.assertEqual(row["current"], 90)
        self.assertEqual(row["currentUrl"], "https://web.joongna.com/product/still-here")

    def test_sold_outliers_are_excluded_from_low6(self):
        sold = [
            self.listing(f"sold-{n}", price, 10 + n, "seller", model="Sold Camera", state="sold", sold_age_days=10 + n)
            for n, price in enumerate([150, 1000, 1100, 1200, 1500])
        ]
        ingest_payload(
            self.connection,
            {"run_id": "fixture-sold", "fetched_at": self.as_of.isoformat(), "listings": sold, "seller_safety_checks": []},
        )
        run_id = compute_price_guide(self.connection, self.as_of.isoformat(), "test-sold-outlier")
        row = next(row for row in display_rows(self.connection, run_id) if row["model"] == "Sold Camera")
        self.assertEqual(row["low6"], 1000)

    def test_sold_listings_from_earlier_days_accumulate(self):
        earlier = self.as_of - timedelta(days=5)
        ingest_payload(
            self.connection,
            {
                "run_id": "fixture-sold-earlier", "fetched_at": earlier.isoformat(),
                "listings": [self.listing("sold-earlier", 70, 30, None, model="Daily Sold", state="sold", sold_age_days=30)],
                "seller_safety_checks": [],
            },
        )
        ingest_payload(
            self.connection,
            {
                "run_id": "fixture-sold-today", "fetched_at": self.as_of.isoformat(),
                "listings": [self.listing("sold-today", 80, 1, None, model="Daily Sold", state="sold", sold_age_days=1)],
                "seller_safety_checks": [],
            },
        )
        run_id = compute_price_guide(self.connection, self.as_of.isoformat(), "test-sold-accumulate")
        row = next(row for row in display_rows(self.connection, run_id) if row["model"] == "Daily Sold")
        self.assertEqual(row["low6"], 70)
        self.assertEqual(row["low6Url"], "https://web.joongna.com/product/sold-earlier")

    def test_exactly_25_days_is_included(self):
        exact = self.listing("exact-25", 100, 25, "safe-seller", model="Boundary")
        too_old = self.listing("older-than-25", 50, 25, "safe-seller", model="Boundary")
        too_old["listed_at"] = (self.as_of - timedelta(days=25, seconds=1)).isoformat()
        too_old["updated_at"] = too_old["listed_at"]
        ingest_payload(
            self.connection,
            {
                "run_id": "fixture-boundary",
                "fetched_at": self.as_of.isoformat(),
                "listings": [exact, too_old],
                "seller_safety_checks": [self.safety("safe-seller", 1)],
            },
        )
        run_id = compute_price_guide(
            self.connection, self.as_of.isoformat(), "test-boundary"
        )
        row = next(row for row in display_rows(self.connection, run_id) if row["model"] == "Boundary")
        self.assertEqual(row["current"], 100)
        self.assertEqual(row["safe"], 100)

    def test_same_day_verified_history_and_note_survive_refresh(self):
        ingest_payload(
            self.connection,
            {
                "run_id": "fixture-preserve",
                "fetched_at": self.as_of.isoformat(),
                "listings": [self.listing("active", 100, 1, None, model="Preserved")],
            },
        )
        product = self.connection.execute(
            "SELECT id FROM products WHERE model = 'Preserved'"
        ).fetchone()["id"]
        self.connection.execute(
            """
            INSERT INTO pricing_runs(
              id, as_of, ruleset_id, current_listing_max_age_days, source_kind,
              source_ref, rules_json, created_at
            ) VALUES ('legacy-preserve', ?, 'legacy', 60, 'legacy_snapshot', NULL, '{}', ?)
            """,
            (self.as_of.isoformat(), self.as_of.isoformat()),
        )
        self.connection.execute(
            """
            INSERT INTO price_guide_rows(
              pricing_run_id, product_id, low6_price_krw, low6_url,
              avg3_price_krw, avg3_sample_size, safety_label, note, sort_order
            ) VALUES ('legacy-preserve', ?, 70, 'https://web.joongna.com/product/history',
                      80, 3, '주의', '기존 검수 메모', 0)
            """,
            (product,),
        )
        self.connection.commit()
        run_id = compute_price_guide(self.connection, self.as_of.isoformat(), "test-preserve")
        row = next(row for row in display_rows(self.connection, run_id) if row["model"] == "Preserved")
        self.assertEqual(row["low6"], 70)
        self.assertEqual(row["low6Url"], "https://web.joongna.com/product/history")
        self.assertEqual(row["avg3"], 80)
        self.assertEqual(row["n3"], 3)
        self.assertEqual(row["note"], "기존 검수 메모")


if __name__ == "__main__":
    unittest.main()
