#!/usr/bin/env python3
"""매일 갱신: 직접 수집 → 정규화 → 90일 평균 → 오래된 스냅샷 정리. DB·사이트 빌드는 make가 맡는다."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.error
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collect_marketplaces import REQUEST_DELAY_SECONDS, bunjang_description, joongna_description, joongna_safe_trade_count  # noqa: E402
from normalize_mcp_refresh import CATALOG, DEFECT_VARIANT, UNKNOWN_CAPACITY_VARIANT, normalize  # noqa: E402

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
# 사이트에 보이는 건 최저가라서 칸마다 싼 매물부터 본문을 확인한다(고장 문구, 제목에 없는 용량).
DETAIL_CHECKS = {"active": 6, "sold": 4}
DETAIL_CHECKS_UNKNOWN_CAPACITY = 12
DETAIL_ROUNDS = 3
# 중고나라 상품 페이지는 몰아서 부르면 한동안 403으로 막는다. 번개장터 API는 여유가 있다.
DETAIL_WORKERS = {"bunjang": 4, "joongna": 2}
BLOCKED_COOLDOWN_SECONDS = 60
BLOCKED_GIVE_UP = 30


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


class DetailFetcher:
    """403이 나면 그 마켓 요청을 모두 잠시 멈췄다가 다시 시도한다. 너무 자주 막히면 이번 회차엔 그 마켓을 포기한다."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.resume_at = {"bunjang": 0.0, "joongna": 0.0}
        self.blocked = Counter()
        self.failed = Counter()

    def wait(self, marketplace: str) -> None:
        delay = self.resume_at[marketplace] - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def fetch(self, marketplace: str, external_id: str) -> str | None:
        for attempt in range(2):
            if self.blocked[marketplace] >= BLOCKED_GIVE_UP:
                return None
            self.wait(marketplace)
            try:
                if marketplace == "bunjang":
                    return bunjang_description(external_id)
                return joongna_description(external_id)
            except urllib.error.HTTPError as error:
                if error.code != 403 or attempt == 1:
                    break
                with self.lock:
                    self.blocked[marketplace] += 1
                    if self.blocked[marketplace] == BLOCKED_GIVE_UP:
                        print(f"{marketplace} 본문 요청이 계속 막혀 이번 회차엔 그만 읽습니다", file=sys.stderr)
                    self.resume_at[marketplace] = max(
                        self.resume_at[marketplace], time.monotonic() + BLOCKED_COOLDOWN_SECONDS
                    )
            except Exception:
                break
            finally:
                time.sleep(REQUEST_DELAY_SECONDS)
        with self.lock:
            self.failed[marketplace] += 1
        return None

    def fetch_all(self, keys: list[tuple[str, str]]) -> dict[tuple[str, str], str]:
        results: dict[tuple[str, str], str] = {}
        for marketplace, workers in DETAIL_WORKERS.items():
            wanted = [key for key in keys if key[0] == marketplace]
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for key, text in zip(wanted, pool.map(lambda key: self.fetch(*key), wanted)):
                    # 못 읽은 매물은 기록하지 않는다. 다음 라운드에 다시 시도하고, 끝내 못 읽으면 제목만으로 분류된다.
                    if text is not None:
                        results[key] = text
        return results


def normalize_with_descriptions(raw: dict, catalog: dict) -> dict:
    """싼 매물의 본문을 읽고 다시 분류한다. 본문 때문에 칸이 바뀌면 새로 최저가가 된 매물도 읽는다."""
    descriptions: dict[tuple[str, str], str] = {}
    attempted: set[tuple[str, str]] = set()
    fetcher = DetailFetcher()
    payload = normalize(raw, catalog, descriptions)
    for _ in range(DETAIL_ROUNDS):
        groups: dict[tuple[str, str, str, str], list[dict]] = {}
        for listing in payload["listings"]:
            if listing["variant"] != DEFECT_VARIANT:
                groups.setdefault((listing["brand"], listing["model"], listing["variant"], listing["state"]), []).append(listing)
        wanted = []
        for (_, _, variant, state), listings in groups.items():
            limit = DETAIL_CHECKS_UNKNOWN_CAPACITY if variant == UNKNOWN_CAPACITY_VARIANT else DETAIL_CHECKS[state]
            listings.sort(key=lambda listing: listing["price_krw"])
            wanted += [
                (listing["marketplace"], listing["external_listing_id"])
                for listing in listings[:limit]
                if (listing["marketplace"], listing["external_listing_id"]) not in attempted
            ]
        if not wanted:
            break
        keys = list(dict.fromkeys(wanted))
        attempted.update(keys)
        descriptions.update(fetcher.fetch_all(keys))
        payload = normalize(raw, catalog, descriptions)
    moved = Counter(listing["variant"] for listing in payload["listings"] if listing["raw"].get("description_checked"))
    print(
        f"본문 확인: {len(descriptions)}건 · 고장 {moved.get(DEFECT_VARIANT, 0)}건"
        f" · 용량 미확인 {moved.get(UNKNOWN_CAPACITY_VARIANT, 0)}건"
        f" · 못 읽음 {dict(fetcher.failed)} · 차단 {dict(fetcher.blocked)}"
    )
    return payload


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
    payload = normalize_with_descriptions(json.loads(raw_path.read_text()), json.loads(CATALOG.read_text()))
    attach_joongna_safety(payload)
    import_path = IMPORTS_DIR / f"{run_id}.json"
    import_path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(f"정규화: {import_path.relative_to(ROOT)} · 매물 {len(payload['listings'])}건")
    if not args.skip_averages:
        run("scripts/refresh_sold_averages.py")
    prune(today)


if __name__ == "__main__":
    main()
