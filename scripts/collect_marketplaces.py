#!/usr/bin/env python3
"""중고나라·번개장터 공개 검색 API에서 직접 매물을 모아 MCP 원본과 같은 형식으로 저장한다."""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERIES = ROOT / "config" / "search-queries.json"
KST = timezone(timedelta(hours=9))

JOONGNA_SEARCH_URL = "https://search-api.joongna.com/v3/search/all"
JOONGNA_STORE_URL = "https://main-api.joongna.com/v2/my-store/{store_seq}"
BUNJANG_SEARCH_URL = "https://api.bunjang.co.kr/api/search/v8/web/search"
BUNJANG_DETAIL_URL = "https://api.bunjang.co.kr/api/pms/v3/products-detail/{pid}?viewerUid=-1"
JOONGNA_PRODUCT_URL = "https://web.joongna.com/product/{seq}"
USER_AGENT = "Mozilla/5.0 (compatible; 55fries-price-guide/1.0; +https://devuterian.github.io/55fries/)"
JOONGNA_ON_SALE = 0
JOONGNA_SOLD = 3
REQUEST_DELAY_SECONDS = 0.4
FAILURE_RATIO_LIMIT = 0.5
# 케이스·필름 같은 싼 글이 검색 페이지를 채우지 않게 검색 단계에서 10만 원 미만은 받지 않는다.
# 에어팟처럼 중고가가 낮은 모델은 config/search-queries.json의 min_price_krw로 낮춘다.
SEARCH_MIN_PRICE_KRW = 100_000


def request_json(url: str, body: dict | None = None, attempts: int = 3) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt * 2)
    raise AssertionError("unreachable")


def request_text(url: str, attempts: int = 3) -> str:
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=20) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            # 403(요청 과다 차단)·404는 바로 다시 불러도 소용없으니 호출한 쪽이 쉬었다가 판단한다.
            if error.code in (403, 404) or attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt * 2)
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(2 ** attempt * 2)
    raise AssertionError("unreachable")


def bunjang_description(pid: str) -> str:
    payload = request_json(BUNJANG_DETAIL_URL.format(pid=urllib.parse.quote(str(pid))))
    return (((payload.get("data") or {}).get("product") or {}).get("description")) or ""


def joongna_description_from_html(html: str) -> str:
    """중고나라는 상세 API가 없어 상품 페이지에 실린 Next.js 데이터에서 본문을 꺼낸다."""
    chunks = []
    for match in re.finditer(r"self\.__next_f\.push\((\[.*?\])\)</script>", html, re.DOTALL):
        try:
            chunk = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if len(chunk) > 1 and isinstance(chunk[1], str):
            chunks.append(chunk[1])
    payload = "".join(chunks)
    found = re.search(r'"productDescription":("(?:[^"\\]|\\.)*")', payload)
    if not found:
        return ""
    value = json.loads(found.group(1))
    reference = re.fullmatch(r"\$([0-9a-f]+)", value)
    if not reference:
        return value
    # "$41"은 같은 응답 안의 "41:T<바이트 길이 16진수>," 텍스트 조각을 가리킨다.
    data = payload.encode()
    header = re.search(rb"(?:^|\n)" + reference.group(1).encode() + rb":T([0-9a-f]+),", data)
    if not header:
        return ""
    start = header.end()
    return data[start:start + int(header.group(1), 16)].decode("utf-8", "replace")


def joongna_description(seq: str) -> str:
    return joongna_description_from_html(request_text(JOONGNA_PRODUCT_URL.format(seq=urllib.parse.quote(str(seq)))))


def joongna_time(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)


def joongna_item(item: dict) -> dict:
    return {
        "sequence": item["seq"],
        "title": item.get("title") or "",
        "price_krw": int(item.get("price") or 0),
        "listing_url": f"https://web.joongna.com/product/{item['seq']}",
        "sorted_at": joongna_time(item["sortDate"]).isoformat(timespec="seconds"),
        "seller_id": item.get("storeSeq"),
        "certified_seller": bool(item.get("certifySellerFlag")),
        "state": item.get("state"),
    }


def collect_joongna(search_word: str, cutoff: datetime, max_pages: int, min_price: int = SEARCH_MIN_PRICE_KRW) -> dict:
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    available: list[dict] = []
    sold: list[dict] = []
    seen: set[int] = set()
    total = None
    for page in range(max_pages):
        payload = request_json(
            JOONGNA_SEARCH_URL,
            {
                "searchWord": search_word, "sort": "RECENT_SORT", "saleYn": "SALE_Y", "page": page,
                "priceFilter": {"minPrice": min_price},
            },
        )
        data = payload.get("data") or {}
        total = data.get("totalSize", total)
        items = [item for item in data.get("items") or [] if item.get("seq") and item.get("sortDate")]
        if not items:
            break
        for item in items:
            if item["seq"] in seen or joongna_time(item["sortDate"]) < cutoff:
                continue
            seen.add(item["seq"])
            if item.get("state") == JOONGNA_ON_SALE:
                available.append(joongna_item(item))
            elif item.get("state") == JOONGNA_SOLD:
                sold.append(joongna_item(item))
        if min(joongna_time(item["sortDate"]) for item in items) < cutoff:
            break
        time.sleep(REQUEST_DELAY_SECONDS)
    return {
        "search_word": search_word,
        "source_url": "https://web.joongna.com/search/" + urllib.parse.quote(search_word),
        "fetched_at": fetched_at,
        "total_count": total,
        "available_listings": available,
        "sold_price_history": {
            "source_key": "SEARCH_SOLD_OUT",
            "label_ko": "판매완료",
            "listing_count": len(sold),
            "listings": sold,
        },
    }


def joongna_safe_trade_count(store_seq: str) -> int | None:
    payload = request_json(JOONGNA_STORE_URL.format(store_seq=urllib.parse.quote(str(store_seq))))
    count = (payload.get("data") or {}).get("safeTradeCount")
    return int(count) if count is not None else None


def bunjang_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def collect_bunjang(search_word: str, cutoff: datetime, max_pages: int, min_price: int = SEARCH_MIN_PRICE_KRW) -> dict:
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    listings: list[dict] = []
    seen: set[int] = set()
    cursor = None
    total = None
    for _ in range(max_pages):
        params = {
            "policyKey": "pw.product.keyword", "q": search_word, "sort": "latest", "size": 60,
            "minPrice": min_price,
        }
        if cursor:
            params["cursor"] = cursor
        payload = request_json(BUNJANG_SEARCH_URL + "?" + urllib.parse.urlencode(params))
        response = (((payload.get("data") or {}).get("responses") or {}).get("mainGrid") or {}).get(
            "searchResponse"
        ) or {}
        total = response.get("totalCount", total)
        items = [
            item for item in response.get("data") or []
            if item.get("type") == "PRODUCT" and not item.get("ad") and item.get("pid") and item.get("updatedAt")
        ]
        for item in items:
            if item["pid"] in seen or item.get("status") != "SELLING" or bunjang_time(item["updatedAt"]) < cutoff:
                continue
            seen.add(item["pid"])
            listings.append(
                {
                    "product_id": item["pid"],
                    "title": item.get("name") or "",
                    "price_krw": int(item.get("price") or 0),
                    "listing_url": f"https://m.bunjang.co.kr/products/{item['pid']}",
                    "updated_at": item["updatedAt"],
                    "seller_id": (item.get("shop") or {}).get("uid"),
                    "seller_name": None,
                    "status": item.get("status"),
                }
            )
        cursor = response.get("cursor")
        if not items or not cursor or min(bunjang_time(item["updatedAt"]) for item in items) < cutoff:
            break
        time.sleep(REQUEST_DELAY_SECONDS)
    return {
        "search_word": search_word,
        "source_url": "https://m.bunjang.co.kr/search/products?q=" + urllib.parse.quote(search_word),
        "fetched_at": fetched_at,
        "total_count": total,
        "listings": listings,
    }


def collect(
    run_id: str, queries: list[dict], days: int, joongna_pages: int, bunjang_pages: int
) -> tuple[dict, list[str]]:
    started = datetime.now(timezone.utc)
    cutoff = started - timedelta(days=days)
    results = []
    failures = []
    for index, query in enumerate(queries, 1):
        model, word = query["model"], query["search_word"]
        entry = {"model": model, "joongna": {}, "bunjang": {}}
        for marketplace, collector, pages in (
            ("joongna", collect_joongna, joongna_pages),
            ("bunjang", collect_bunjang, bunjang_pages),
        ):
            try:
                entry[marketplace] = collector(word, cutoff, pages, query.get("min_price_krw", SEARCH_MIN_PRICE_KRW))
            except Exception as error:  # 한 모델 실패가 전체 수집을 멈추지 않게 기록만 한다
                failures.append(f"{model} / {marketplace}: {error}")
                entry[marketplace] = {"search_word": word, "error": str(error)}
            time.sleep(REQUEST_DELAY_SECONDS)
        joongna = entry["joongna"]
        print(
            f"[{index}/{len(queries)}] {model}: 중고나라 판매중 {len(joongna.get('available_listings') or [])}"
            f" · 판매완료 {len((joongna.get('sold_price_history') or {}).get('listings') or [])}"
            f" · 번개장터 {len(entry['bunjang'].get('listings') or [])}",
            flush=True,
        )
        results.append(entry)
    raw = {
        "schema_version": 1,
        "run_id": run_id,
        "fetched_at": started.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "queries": results,
    }
    return raw, failures


def main() -> None:
    parser = argparse.ArgumentParser(description="중고나라·번개장터 매물 직접 수집")
    parser.add_argument("output", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--days", type=int, default=25, help="이 기간 안에 올라오거나 끌어올린 매물만 수집")
    parser.add_argument("--joongna-pages", type=int, default=10, help="모델당 최대 페이지(40개씩)")
    parser.add_argument("--bunjang-pages", type=int, default=5, help="모델당 최대 페이지(60개씩)")
    parser.add_argument("--models", nargs="*", help="일부 모델만 수집(점검용)")
    args = parser.parse_args()
    queries = json.loads(QUERIES.read_text())["queries"]
    if args.models:
        queries = [query for query in queries if query["model"] in set(args.models)]
        if not queries:
            raise SystemExit("요청한 모델이 config/search-queries.json에 없습니다")
    raw, failures = collect(args.run_id, queries, args.days, args.joongna_pages, args.bunjang_pages)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(raw, ensure_ascii=False, separators=(",", ":")) + "\n")
    for failure in failures:
        print(f"수집 실패: {failure}", file=sys.stderr)
    if len(failures) > len(queries) * 2 * FAILURE_RATIO_LIMIT:
        raise SystemExit(f"수집 실패가 너무 많습니다: {len(failures)}건")


if __name__ == "__main__":
    main()
