#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
import statistics
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEOUL = timezone(timedelta(hours=9))
DEFAULT_DB = ROOT / "var" / "salmanhanga.sqlite"
RULES_PATH = ROOT / "config" / "pricing-rules.json"
LEGACY_DATA_PATH = ROOT / "data" / "imports" / "legacy-2026-09-20.json"
SOURCE_HTML_PATH = ROOT / "src" / "index.html"
CATALOG_PATH = ROOT / "data" / "catalog" / "products.json"
SOLD_AVERAGES_DIR = ROOT / "data" / "aggregates"


def stable_id(prefix: str, *parts: object) -> str:
    raw = "\x1f".join("" if part is None else str(part).strip() for part in parts)
    return f"{prefix}_{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=SEOUL) if parsed.tzinfo is None else parsed


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def connect(path: Path | str = DEFAULT_DB) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    applied = {row[0] for row in connection.execute("SELECT version FROM schema_migrations")}
    for migration in sorted((ROOT / "db" / "migrations").glob("*.sql")):
        if migration.name in applied:
            continue
        connection.executescript(migration.read_text())
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (migration.name, iso(datetime.now(timezone.utc))),
        )
    connection.executemany(
        "INSERT OR IGNORE INTO marketplaces(code, name_ko, base_url) VALUES (?, ?, ?)",
        [
            ("bunjang", "번개장터", "https://m.bunjang.co.kr"),
            ("joongna", "중고나라", "https://web.joongna.com"),
        ],
    )
    connection.commit()


def marketplace_from_url(url: str) -> str:
    if "bunjang.co.kr" in url:
        return "bunjang"
    if "joongna.com" in url:
        return "joongna"
    raise ValueError(f"지원하지 않는 매물 URL: {url}")


def external_id_from_url(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1]


def product_id(brand: str, model: str, variant: str) -> str:
    return stable_id("product", brand.casefold(), model.casefold(), variant.casefold())


def upsert_product(
    connection: sqlite3.Connection, brand: str, model: str, variant: str, created_at: str
) -> str:
    identifier = product_id(brand, model, variant)
    connection.execute(
        """
        INSERT INTO products(id, brand, model, variant, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET brand=excluded.brand, model=excluded.model, variant=excluded.variant
        """,
        (identifier, brand, model, variant, created_at),
    )
    return identifier


def sync_catalog(connection: sqlite3.Connection) -> None:
    created_at = iso(datetime.now(timezone.utc))
    for item in json.loads(CATALOG_PATH.read_text())["products"]:
        upsert_product(connection, item["brand"], item["model"], item["variant"], created_at)
    connection.commit()


def upsert_seller(
    connection: sqlite3.Connection,
    marketplace: str,
    external_seller_id: str | None,
    display_name: str | None,
    created_at: str,
) -> str | None:
    if not external_seller_id:
        return None
    identifier = stable_id("seller", marketplace, external_seller_id)
    connection.execute(
        """
        INSERT INTO sellers(id, marketplace_code, external_seller_id, display_name, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET display_name=COALESCE(excluded.display_name, sellers.display_name)
        """,
        (identifier, marketplace, external_seller_id, display_name, created_at),
    )
    return identifier


def upsert_listing(
    connection: sqlite3.Connection,
    *, marketplace: str, external_listing_id: str, product: str, seller: str | None,
    listing_url: str, listed_at: str | None, updated_at: str | None, sold_at: str | None,
    fetched_at: str, is_comparable: bool, exclusion_reason: str | None, raw: object | None,
) -> str:
    identifier = stable_id("listing", marketplace, external_listing_id)
    connection.execute(
        """
        INSERT INTO listings(
          id, marketplace_code, external_listing_id, product_id, seller_id, listing_url,
          listed_at, updated_at, sold_at, fetched_at, is_comparable, exclusion_reason, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          product_id=excluded.product_id,
          seller_id=COALESCE(excluded.seller_id, listings.seller_id),
          listing_url=excluded.listing_url,
          listed_at=COALESCE(excluded.listed_at, listings.listed_at),
          updated_at=COALESCE(excluded.updated_at, listings.updated_at),
          sold_at=COALESCE(excluded.sold_at, listings.sold_at),
          fetched_at=excluded.fetched_at,
          is_comparable=excluded.is_comparable,
          exclusion_reason=excluded.exclusion_reason,
          raw_json=COALESCE(excluded.raw_json, listings.raw_json)
        """,
        (
            identifier, marketplace, external_listing_id, product, seller, listing_url,
            listed_at, updated_at, sold_at, fetched_at, int(is_comparable), exclusion_reason,
            json.dumps(raw, ensure_ascii=False, separators=(",", ":")) if raw is not None else None,
        ),
    )
    return identifier


def extract_legacy_rows(html: str) -> list[dict]:
    match = re.search(r"const DATA=(\[.*\]);\nconst won=", html, re.DOTALL)
    if not match:
        raise ValueError("src/index.html에서 const DATA를 찾지 못했습니다")
    return json.loads(match.group(1))


def record_ingestion_run(
    connection: sqlite3.Connection,
    run_id: str,
    fetched_at: str,
    payload: object,
    source_ref: str | None,
) -> None:
    compact = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    connection.execute(
        """
        INSERT INTO ingestion_runs(id, fetched_at, source_ref, payload_sha256, imported_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
          fetched_at=excluded.fetched_at,
          source_ref=COALESCE(excluded.source_ref, ingestion_runs.source_ref),
          payload_sha256=excluded.payload_sha256,
          imported_at=excluded.imported_at
        """,
        (
            run_id,
            fetched_at,
            source_ref,
            hashlib.sha256(compact.encode()).hexdigest(),
            iso(datetime.now(timezone.utc)),
        ),
    )


def import_legacy(connection: sqlite3.Connection) -> None:
    legacy = json.loads(LEGACY_DATA_PATH.read_text())
    rows = [
        {
            "brand": row["brand"],
            "model": row["model"],
            "variant": row.get("variant", ""),
            "current": row.get("current_low_temp"),
            "currentUrl": row.get("current_low_url"),
            "safe": row.get("current_safe"),
            "safeUrl": row.get("current_safe_url"),
            "low6": row.get("six_month_low"),
            "low6Url": row.get("six_month_low_url"),
            "avg3": row.get("three_month_avg"),
            "n3": row.get("three_month_n", 0),
            "note": row.get("note", ""),
            "safety": row.get("safety_status", "주의 · 안전거래 이력 확인불가"),
        }
        for row in legacy["rows"]
    ]
    catalog = json.loads(CATALOG_PATH.read_text())["products"]
    catalog_keys = {(item["brand"], item["model"], item["variant"]) for item in catalog}
    visible_keys = {(row["brand"], row["model"], row.get("variant", "")) for row in rows}
    missing_keys = visible_keys - catalog_keys
    if missing_keys:
        raise ValueError("레거시 사이트 상품이 상품 카탈로그에 없습니다")
    as_of = parse_time(legacy["as_of_kst"])
    assert as_of is not None
    as_of_text = iso(as_of)
    run_id = "legacy-2026-09-20"
    connection.execute(
        "DELETE FROM listing_observations WHERE ingestion_run_id = ?", (run_id,)
    )
    record_ingestion_run(
        connection,
        run_id,
        as_of_text,
        legacy,
        str(LEGACY_DATA_PATH.relative_to(ROOT)),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO pricing_runs(
          id, as_of, ruleset_id, current_listing_max_age_days, source_kind,
          source_ref, rules_json, created_at
        ) VALUES (?, ?, ?, ?, 'legacy_snapshot', ?, ?, ?)
        """,
        (
            run_id, as_of_text, "legacy-2026-09-20-60d",
            int(legacy["rules"]["current_listing_max_age_days"]),
            str(LEGACY_DATA_PATH.relative_to(ROOT)),
            json.dumps(legacy["rules"], ensure_ascii=False, separators=(",", ":")),
            as_of_text,
        ),
    )
    for order, row in enumerate(rows):
        product = upsert_product(
            connection, row["brand"], row["model"], row.get("variant", ""), as_of_text
        )
        listing_ids: dict[str, str | None] = {"current": None, "safe": None, "low6": None}
        for role, price_key, url_key, state in [
            ("current", "current", "currentUrl", "active"),
            ("safe", "safe", "safeUrl", "active"),
            ("low6", "low6", "low6Url", "sold"),
        ]:
            url = row.get(url_key)
            price = row.get(price_key)
            if not url or price is None:
                continue
            marketplace = marketplace_from_url(url)
            listing = upsert_listing(
                connection,
                marketplace=marketplace,
                external_listing_id=external_id_from_url(url),
                product=product,
                seller=None,
                listing_url=url,
                listed_at=None,
                updated_at=None,
                sold_at=None,
                fetched_at=as_of_text,
                is_comparable=True,
                exclusion_reason=None,
                raw={"legacy_role": role},
            )
            connection.execute(
                """
                INSERT INTO listing_observations(
                  listing_id, observed_at, title, price_krw, state, raw_json, ingestion_run_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(listing_id, observed_at) DO UPDATE SET
                  ingestion_run_id=excluded.ingestion_run_id
                """,
                (
                    listing, as_of_text, f"{row['model']} {row.get('variant', '')}".strip(),
                    price, state, json.dumps({"legacy_role": role}, ensure_ascii=False), run_id,
                ),
            )
            listing_ids[role] = listing
        connection.execute(
            """
            INSERT OR REPLACE INTO price_guide_rows(
              pricing_run_id, product_id,
              current_listing_id, current_price_krw, current_url,
              safe_listing_id, safe_price_krw, safe_url,
              low6_listing_id, low6_price_krw, low6_url,
              avg3_price_krw, avg3_sample_size, safety_label, note, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, product,
                listing_ids["current"], row.get("current"), row.get("currentUrl"),
                listing_ids["safe"], row.get("safe"), row.get("safeUrl"),
                listing_ids["low6"], row.get("low6"), row.get("low6Url"),
                row.get("avg3"), row.get("n3", 0),
                row.get("safety", "주의 · 안전거래 이력 확인불가"),
                row.get("note", ""), order,
            ),
        )
    connection.commit()


def require_fields(record: dict, required: set[str], context: str) -> None:
    missing = sorted(required - record.keys())
    if missing:
        raise ValueError(f"{context} 필수 필드 누락: {', '.join(missing)}")


def ingest_payload(
    connection: sqlite3.Connection, payload: dict, source_ref: str | None = None
) -> None:
    require_fields(payload, {"run_id", "fetched_at", "listings"}, "수집 실행")
    fetched_at = iso(parse_time(payload["fetched_at"]) or datetime.now(SEOUL))
    connection.execute(
        "DELETE FROM seller_safety_checks WHERE ingestion_run_id = ?", (payload["run_id"],)
    )
    connection.execute(
        "DELETE FROM listing_observations WHERE ingestion_run_id = ?", (payload["run_id"],)
    )
    record_ingestion_run(connection, payload["run_id"], fetched_at, payload, source_ref)
    listing_fields = {
        "marketplace", "external_listing_id", "brand", "model", "variant", "title",
        "listing_url", "price_krw", "state",
    }
    for index, record in enumerate(payload["listings"]):
        require_fields(record, listing_fields, f"listings[{index}]")
        if record["marketplace"] not in {"bunjang", "joongna"}:
            raise ValueError(f"지원하지 않는 마켓: {record['marketplace']}")
        product = upsert_product(
            connection, record["brand"], record["model"], record.get("variant", ""), fetched_at
        )
        seller = upsert_seller(
            connection, record["marketplace"], record.get("seller_external_id"),
            record.get("seller_name"), fetched_at,
        )
        listing = upsert_listing(
            connection,
            marketplace=record["marketplace"],
            external_listing_id=str(record["external_listing_id"]),
            product=product,
            seller=seller,
            listing_url=record["listing_url"],
            listed_at=record.get("listed_at"),
            updated_at=record.get("updated_at"),
            sold_at=record.get("sold_at"),
            fetched_at=fetched_at,
            is_comparable=record.get("is_comparable", True),
            exclusion_reason=record.get("exclusion_reason"),
            raw=record.get("raw"),
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO listing_observations(
              listing_id, observed_at, title, price_krw, state, raw_json, ingestion_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                listing, fetched_at, record["title"], int(record["price_krw"]), record["state"],
                json.dumps(record.get("raw"), ensure_ascii=False) if record.get("raw") else None,
                payload["run_id"],
            ),
        )
    safety_fields = {"marketplace", "seller_external_id", "checked_at", "verification_status"}
    for index, record in enumerate(payload.get("seller_safety_checks", [])):
        require_fields(record, safety_fields, f"seller_safety_checks[{index}]")
        status = record["verification_status"]
        count = record.get("safe_trade_count")
        if status == "verified" and count is None:
            raise ValueError("verified 안전거래 확인에는 safe_trade_count가 필요합니다")
        if status == "unavailable":
            count = None
        seller = upsert_seller(
            connection, record["marketplace"], str(record["seller_external_id"]), None, fetched_at
        )
        assert seller is not None
        connection.execute(
            """
            INSERT OR REPLACE INTO seller_safety_checks(
              seller_id, checked_at, verification_status, safe_trade_count, source_url, raw_json,
              ingestion_run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                seller, record["checked_at"], status, count, record.get("source_url"),
                json.dumps(record.get("raw"), ensure_ascii=False) if record.get("raw") else None,
                payload["run_id"],
            ),
        )
    connection.commit()


def latest_safety(connection: sqlite3.Connection, seller_id: str | None, as_of: str) -> sqlite3.Row | None:
    if not seller_id:
        return None
    return connection.execute(
        """
        SELECT verification_status, safe_trade_count
        FROM seller_safety_checks
        WHERE seller_id = ? AND checked_at <= ?
        ORDER BY checked_at DESC, id DESC
        LIMIT 1
        """,
        (seller_id, as_of),
    ).fetchone()


def safety_state(check: sqlite3.Row | None, minimum: int) -> str:
    if check is None or check["verification_status"] != "verified":
        return "unavailable"
    return "safe" if check["safe_trade_count"] >= minimum else "zero"


def compute_price_guide(
    connection: sqlite3.Connection, as_of_value: str, run_id: str | None = None,
    rules_path: Path = RULES_PATH,
) -> str:
    rules = json.loads(rules_path.read_text())
    as_of_dt = parse_time(as_of_value)
    if as_of_dt is None:
        raise ValueError("as_of가 필요합니다")
    as_of_text = iso(as_of_dt)
    run_id = run_id or stable_id("guide", rules["ruleset_id"], as_of_text)
    connection.execute(
        """
        INSERT INTO pricing_runs(
          id, as_of, ruleset_id, current_listing_max_age_days, source_kind,
          source_ref, rules_json, created_at
        ) VALUES (?, ?, ?, ?, 'normalized_listings', NULL, ?, ?)
        """,
        (
            run_id, as_of_text, rules["ruleset_id"], rules["current_listing_max_age_days"],
            json.dumps(rules, ensure_ascii=False, separators=(",", ":")),
            iso(datetime.now(timezone.utc)),
        ),
    )
    observations = connection.execute(
        """
        SELECT l.*, o.title, o.price_krw, o.state, o.observed_at
        FROM listings l
        JOIN listing_observations o ON o.listing_id = l.id
        WHERE o.observed_at = (
          SELECT MAX(o2.observed_at)
          FROM listing_observations o2
          WHERE o2.listing_id = l.id AND o2.observed_at <= ?
            AND substr(o2.observed_at, 1, 10) = substr(?, 1, 10)
        )
        """,
        (as_of_text, as_of_text),
    ).fetchall()
    by_product: dict[str, list[sqlite3.Row]] = {}
    for row in observations:
        by_product.setdefault(row["product_id"], []).append(row)
    products = connection.execute("SELECT * FROM products ORDER BY brand, model, variant").fetchall()
    cutoff = as_of_dt - timedelta(days=int(rules["current_listing_max_age_days"]))
    low6_cutoff = as_of_dt - timedelta(days=180)
    avg3_cutoff = as_of_dt - timedelta(days=90)
    sold_average_files = sorted(SOLD_AVERAGES_DIR.glob("sold-averages-*.json"))
    sold_averages = {}
    for path in sold_average_files:
        sold_averages.update({row["model"]: row for row in json.loads(path.read_text())["rows"]})
    for order, product in enumerate(products):
        items = by_product.get(product["id"], [])
        active: list[sqlite3.Row] = []
        sold6: list[sqlite3.Row] = []
        sold3: list[sqlite3.Row] = []
        for item in items:
            if not item["is_comparable"]:
                continue
            freshness = parse_time(item["updated_at"] or item["listed_at"])
            if item["state"] == "active" and freshness and cutoff <= freshness <= as_of_dt:
                active.append(item)
            sold_at = parse_time(item["sold_at"])
            if item["state"] == "sold" and sold_at and low6_cutoff <= sold_at <= as_of_dt:
                sold6.append(item)
                if avg3_cutoff <= sold_at:
                    sold3.append(item)
        if len(sold6) >= 3:
            # 액세서리·묶음 판매가 섞이므로 판매완료 중앙값의 0.5~1.75배 밖은 제외한다(3개월 평균과 같은 규칙).
            median = statistics.median(row["price_krw"] for row in sold6)
            sold6 = [row for row in sold6 if median * 0.5 <= row["price_krw"] <= median * 1.75]
            sold3 = [row for row in sold3 if median * 0.5 <= row["price_krw"] <= median * 1.75]
        active.sort(key=lambda row: (row["price_krw"], row["listing_url"]))
        current = active[0] if active else None
        safe = None
        for item in active:
            check = latest_safety(connection, item["seller_id"], as_of_text)
            if safety_state(check, int(rules["safe_trade_min_count"])) == "safe":
                safe = item
                break
        sold6.sort(key=lambda row: (row["price_krw"], row["listing_url"]))
        low6 = sold6[0] if sold6 else None
        low6_from_listings = low6 is not None
        low6_listing_id = low6["id"] if low6 else None
        low6_price = low6["price_krw"] if low6 else None
        low6_url = low6["listing_url"] if low6 else None
        avg3 = round(sum(row["price_krw"] for row in sold3) / len(sold3)) if sold3 else None
        avg3_sample_size = len(sold3)
        preserved = connection.execute(
            """
            SELECT g.low6_listing_id, g.low6_price_krw, g.low6_url,
                   g.avg3_price_krw, g.avg3_sample_size, g.note
            FROM price_guide_rows g
            JOIN pricing_runs r ON r.id = g.pricing_run_id
            WHERE g.product_id = ?
              AND r.source_kind = 'legacy_snapshot'
              AND substr(r.as_of, 1, 10) = substr(?, 1, 10)
            ORDER BY r.as_of DESC
            LIMIT 1
            """,
            (product["id"], as_of_text),
        ).fetchone()
        if low6_price is None and preserved is not None and preserved["low6_price_krw"] is not None:
            low6_listing_id = preserved["low6_listing_id"]
            low6_price = preserved["low6_price_krw"]
            low6_url = preserved["low6_url"]
        if avg3 is None and preserved is not None:
            if preserved["avg3_price_krw"] is not None:
                avg3 = preserved["avg3_price_krw"]
                avg3_sample_size = preserved["avg3_sample_size"]
        note = preserved["note"] if preserved is not None else ""
        aggregate = sold_averages.get(product["model"])
        if aggregate and aggregate["average_price_krw"] is not None:
            avg3 = aggregate["average_price_krw"]
            avg3_sample_size = aggregate["sample_size"]
            aggregate_note = "3개월 평균은 중고나라 판매가 차트 기준(모델 전체 구성 혼합, 개별 매물 링크 없음)."
            note = f"{note} {aggregate_note}".strip()
        if low6_from_listings or (avg3 is not None and not aggregate and sold3):
            note = f"{note} 판매완료는 검색 첫 페이지(최근순)만 봤고 판매 시각은 마지막 수정 시각으로 근사.".strip()
        missing_history = []
        if low6_price is None:
            missing_history.append("6개월 판매완료 최저가")
        if avg3 is None:
            missing_history.append("3개월 판매완료 평균가")
        if missing_history:
            missing_note = " · ".join(missing_history) + " 표본 미확보"
            note = f"{note} {missing_note}".strip()
        if current is None:
            label = "현재 판매중 정상 후보 없음"
        else:
            state = safety_state(
                latest_safety(connection, current["seller_id"], as_of_text),
                int(rules["safe_trade_min_count"]),
            )
            label = {
                "safe": rules["safe_label"],
                "zero": rules["caution_label_zero"],
                "unavailable": rules["caution_label_unavailable"],
            }[state]
        connection.execute(
            """
            INSERT INTO price_guide_rows(
              pricing_run_id, product_id,
              current_listing_id, current_price_krw, current_url,
              safe_listing_id, safe_price_krw, safe_url,
              low6_listing_id, low6_price_krw, low6_url,
              avg3_price_krw, avg3_sample_size, safety_label, note, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id, product["id"],
                current["id"] if current else None,
                current["price_krw"] if current else None,
                current["listing_url"] if current else None,
                safe["id"] if safe else None,
                safe["price_krw"] if safe else None,
                safe["listing_url"] if safe else None,
                low6_listing_id, low6_price, low6_url,
                avg3, avg3_sample_size, label, note, order,
            ),
        )
    connection.commit()
    return run_id


def display_rows(connection: sqlite3.Connection, run_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT p.brand, p.model, p.variant, g.*
        FROM price_guide_rows g
        JOIN products p ON p.id = g.product_id
        WHERE g.pricing_run_id = ?
        ORDER BY g.sort_order
        """,
        (run_id,),
    ).fetchall()
    return [
        {
            "brand": row["brand"], "model": row["model"], "variant": row["variant"],
            "current": row["current_price_krw"], "currentUrl": row["current_url"],
            "safe": row["safe_price_krw"], "safeUrl": row["safe_url"],
            "safety": row["safety_label"],
            "low6": row["low6_price_krw"], "low6Url": row["low6_url"],
            "avg3": row["avg3_price_krw"], "n3": row["avg3_sample_size"],
            "note": row["note"],
        }
        for row in rows
    ]


def latest_run(connection: sqlite3.Connection) -> sqlite3.Row:
    run = connection.execute(
        "SELECT * FROM pricing_runs ORDER BY as_of DESC, created_at DESC LIMIT 1"
    ).fetchone()
    if run is None:
        raise ValueError("가격 집계 실행이 없습니다")
    return run


def build_site(connection: sqlite3.Connection, output: Path) -> None:
    run = latest_run(connection)
    output.mkdir(parents=True, exist_ok=True)
    if run["source_kind"] == "legacy_snapshot":
        shutil.copyfile(SOURCE_HTML_PATH, output / "index.html")
        shutil.copyfile(ROOT / run["source_ref"], output / "data.json")
        return
    rows = display_rows(connection, run["id"])
    html = SOURCE_HTML_PATH.read_text()
    replacement = "const DATA=" + json.dumps(rows, ensure_ascii=False, separators=(",", ":")) + ";\nconst won="
    html, count = re.subn(r"const DATA=\[.*\];\nconst won=", replacement, html, count=1, flags=re.DOTALL)
    if count != 1:
        raise ValueError("사이트 DATA 교체에 실패했습니다")
    rules = json.loads(run["rules_json"])
    html = re.sub(
        r"판매중은 최근 \d+일 이내만",
        f"판매중은 최근 {rules['current_listing_max_age_days']}일 이내만",
        html,
        count=1,
    )
    payload = {
        "as_of_kst": run["as_of"], "status": "normalized",
        "rules": rules, "rows": rows,
    }
    (output / "index.html").write_text(html)
    (output / "data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def verify(connection: sqlite3.Connection) -> None:
    rules = json.loads(RULES_PATH.read_text())
    if rules["current_listing_max_age_days"] != 25:
        raise ValueError("판매중 매물 기준은 25일이어야 합니다")
    expected_order = ["판매중 최저가", "판매중-안전", "6개월 최저", "3개월 평균"]
    if rules["current_low_order"] != expected_order:
        raise ValueError("가격 표시 순서가 바뀌었습니다")
    for row in connection.execute("SELECT current_url, safe_url, low6_url FROM price_guide_rows"):
        for url in row:
            if url and not (
                url.startswith("https://web.joongna.com/")
                or url.startswith("https://m.bunjang.co.kr/")
            ):
                raise ValueError(f"허용되지 않은 매물 링크: {url}")
    html = (ROOT / "dist" / "index.html").read_text()
    visible_order = ["판매중 최저가", "6개월 최저", "3개월 평균"]
    positions = [html.index(label) for label in visible_order]
    if positions != sorted(positions):
        raise ValueError("dist 가격 표시 순서가 바뀌었습니다")
    if "<th>판매중-안전</th>" in html or "priceCell('판매중-안전'" in html:
        raise ValueError("판매중-안전 열이 화면에 다시 노출됐습니다")
    if "주의 · 안전거래 이력 확인불가" not in html:
        raise ValueError("안전거래 이력 확인불가 표시가 사라졌습니다")
    with tempfile.TemporaryDirectory() as temp:
        candidate = Path(temp)
        build_site(connection, candidate)
        for name in ("index.html", "data.json"):
            if (candidate / name).read_bytes() != (ROOT / "dist" / name).read_bytes():
                raise ValueError(f"dist/{name}이 DB 최신 실행과 일치하지 않습니다")


def main() -> None:
    parser = argparse.ArgumentParser(description="살만한가 SQLite 및 정적 사이트 관리")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init")
    subparsers.add_parser("bootstrap")
    ingest_parser = subparsers.add_parser("ingest")
    ingest_parser.add_argument("path", type=Path)
    compute_parser = subparsers.add_parser("compute")
    compute_parser.add_argument("--as-of", required=True)
    compute_parser.add_argument("--run-id")
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--output", type=Path, default=ROOT / "dist")
    subparsers.add_parser("verify")
    args = parser.parse_args()
    connection = connect(args.db)
    migrate(connection)
    sync_catalog(connection)
    if args.command == "bootstrap":
        import_legacy(connection)
        imports = [
            (path, json.loads(path.read_text()))
            for path in (ROOT / "data" / "imports").glob("*.json")
            if not path.name.startswith("legacy-")
        ]
        imports.sort(key=lambda item: parse_time(item[1]["fetched_at"]) or datetime.min.replace(tzinfo=timezone.utc))
        for path, payload in imports:
            ingest_payload(connection, payload, str(path.relative_to(ROOT)))
            connection.execute("DELETE FROM price_guide_rows WHERE pricing_run_id = ?", (payload["run_id"],))
            connection.execute("DELETE FROM pricing_runs WHERE id = ?", (payload["run_id"],))
            connection.commit()
            compute_price_guide(connection, payload["fetched_at"], payload["run_id"])
    elif args.command == "ingest":
        ingest_payload(
            connection,
            json.loads(args.path.read_text()),
            str(args.path.resolve().relative_to(ROOT)) if args.path.resolve().is_relative_to(ROOT) else str(args.path),
        )
    elif args.command == "compute":
        print(compute_price_guide(connection, args.as_of, args.run_id))
    elif args.command == "build":
        build_site(connection, args.output)
    elif args.command == "verify":
        verify(connection)
    connection.close()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, sqlite3.Error) as error:
        print(f"오류: {error}", file=sys.stderr)
        raise SystemExit(1)
