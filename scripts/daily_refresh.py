#!/usr/bin/env python3
"""매일 갱신: 직접 수집 → 정규화 → 90일 평균 → 오래된 스냅샷 정리. DB·사이트 빌드는 make가 맡는다."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collect_marketplaces import joongna_safe_trade_count  # noqa: E402
from normalize_mcp_refresh import CATALOG, normalize  # noqa: E402

KST = timezone(timedelta(hours=9))
IMPORTS_DIR = ROOT / "data" / "imports"
AGGREGATES_DIR = ROOT / "data" / "aggregates"
RAW_DIR = ROOT / "var" / "raw"
AUTO_PREFIX = "auto-"
# 6개월 최저가(180일)를 계산할 수 있을 만큼만 스냅샷을 남긴다.
KEEP_IMPORT_DAYS = 190
KEEP_AGGREGATE_FILES = 30
# 모델·구성마다 싼 중고나라 매물부터 판매자 안전거래 횟수를 확인한다. 안전 판매자를 찾으면 멈춘다.
SAFETY_CHECKS_PER_PRODUCT = 10


def attach_joongna_safety(payload: dict) -> None:
    checked_at = payload["fetched_at"]
    counts: dict[str, int | None] = {}
    by_product: dict[tuple[str, str, str], list[dict]] = {}
    for listing in payload["listings"]:
        if listing["marketplace"] == "joongna" and listing["state"] == "active" and listing["seller_external_id"]:
            by_product.setdefault((listing["brand"], listing["model"], listing["variant"]), []).append(listing)
    for listings in by_product.values():
        listings.sort(key=lambda listing: listing["price_krw"])
        for listing in listings[:SAFETY_CHECKS_PER_PRODUCT]:
            seller = listing["seller_external_id"]
            if seller not in counts:
                try:
                    counts[seller] = joongna_safe_trade_count(seller)
                except Exception as error:
                    print(f"안전거래 확인 실패: {seller}: {error}", file=sys.stderr)
                    counts[seller] = None
            if counts[seller]:
                break
    # 확인 못 한 판매자는 기록하지 않는다. 예전에 확인한 횟수를 '확인불가'로 덮지 않기 위해서다.
    payload["seller_safety_checks"] = [
        {
            "marketplace": "joongna",
            "seller_external_id": seller,
            "checked_at": checked_at,
            "verification_status": "verified",
            "safe_trade_count": count,
            "source_url": f"https://web.joongna.com/store/{seller}",
            "raw": {"source_field": "safeTradeCount"},
        }
        for seller, count in sorted(counts.items())
        if count is not None
    ]
    zero = sum(1 for count in counts.values() if count == 0)
    print(f"중고나라 판매자 안전거래 확인: {len(payload['seller_safety_checks'])}명 (0회 {zero}명)")


def snapshot_date(path: Path, prefix: str) -> date | None:
    try:
        return date.fromisoformat(path.stem.removeprefix(prefix))
    except ValueError:
        return None


def prune(today: date) -> None:
    for path in IMPORTS_DIR.glob(f"{AUTO_PREFIX}*.json"):
        day = snapshot_date(path, AUTO_PREFIX)
        if day and (today - day).days > KEEP_IMPORT_DAYS:
            path.unlink()
            print(f"정리: {path.relative_to(ROOT)}")
    aggregates = sorted(
        (path for path in AGGREGATES_DIR.glob("sold-averages-*.json") if snapshot_date(path, "sold-averages-")),
        key=lambda path: path.name,
    )
    for path in aggregates[:-KEEP_AGGREGATE_FILES]:
        path.unlink()
        print(f"정리: {path.relative_to(ROOT)}")


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="55FRIES 일일 갱신")
    parser.add_argument("--days", type=int, default=25, help="수집 기간(첫 실행은 180으로 6개월치 판매완료를 채움)")
    parser.add_argument("--joongna-pages", type=int, default=10)
    parser.add_argument("--bunjang-pages", type=int, default=5)
    parser.add_argument("--skip-averages", action="store_true", help="90일 평균 갱신 생략")
    args = parser.parse_args()

    today = datetime.now(KST).date()
    run_id = f"{AUTO_PREFIX}{today.isoformat()}"
    raw_path = RAW_DIR / f"{run_id}.json"
    run(
        "scripts/collect_marketplaces.py", str(raw_path), "--run-id", run_id,
        "--days", str(args.days),
        "--joongna-pages", str(args.joongna_pages),
        "--bunjang-pages", str(args.bunjang_pages),
    )
    payload = normalize(json.loads(raw_path.read_text()), json.loads(CATALOG.read_text()))
    attach_joongna_safety(payload)
    import_path = IMPORTS_DIR / f"{run_id}.json"
    import_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"정규화: {import_path.relative_to(ROOT)} · 매물 {len(payload['listings'])}건")
    if not args.skip_averages:
        run("scripts/refresh_sold_averages.py")
    prune(today)


if __name__ == "__main__":
    main()
