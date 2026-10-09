#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
AGGREGATES = ROOT / "data" / "aggregates"
KST = timezone(timedelta(hours=9))
API_URL = "https://search-api.joongna.com/v4/analysis/product-price/scatter-plot"
WINDOW_DAYS = 90
DISCOUNT_PERCENT = 15
ROUNDING_KRW = 10_000

SPECS = [
    ("Galaxy S22 Ultra", "갤럭시 S22 울트라", 150_000, ["갤럭시 s22 울트라"]),
    ("Galaxy S23 Ultra", "갤럭시 S23 울트라", 150_000, ["갤럭시 s23 울트라"]),
    ("Galaxy S22", "갤럭시 S22", 150_000, ["갤럭시 s22"]),
    ("Galaxy S23", "갤럭시 S23", 150_000, ["갤럭시 s23"]),
    ("iPhone 14 Pro", "아이폰 14 프로", 150_000, ["아이폰 14 프로"]),
    ("iPhone 14 Pro Max", "아이폰 14 프로 맥스", 150_000, ["아이폰 14 프로 맥스"]),
    ("Ricoh GR IV", "리코 GR4", 500_000, ["리코 gr4"]),
    ("Sony RX100 VII", "소니 RX100M7", 500_000, ["소니 RX100 VII"]),
    ("Panasonic TZ99 / ZS99", "파나소닉 TZ99", 300_000, ["파나소닉 TZ99"]),
    ("Insta360 X6", "인스타360 X6", 300_000, ["인스타360 x6"]),
    ("DJI Mini 5 Pro", "DJI 미니 5 프로", 500_000, ["DJI 미니 5 프로"]),
    ("DJI Air 3S", "DJI 에어 3S", 700_000, ["dji 에어 3s"]),
    ("DJI Mavic 4 Pro", "DJI 매빅 4 프로", 1_500_000, ["dji 매빅 4 프로"]),
    ("MacBook Air M4", "맥북 에어 M4", 700_000, ["맥북 에어 m4"]),
    ("MacBook Pro M4 Pro", "맥북 프로 M4 프로", 700_000, ["맥북 프로 M4 프로"]),
    ("MacBook Pro M4 Max", "맥북프로 M4 MAX", 700_000, ["맥북 프로 M4 맥스"]),
    ("Apple Watch Series 10", "애플워치10", 150_000, ["애플워치 시리즈10"]),
    ("Apple Watch Ultra 2", "애플워치 울트라2", 150_000, ["애플워치 울트라2"]),
    ("Galaxy S24 Ultra", "갤럭시 S24 울트라", 150_000, ["갤럭시 s24 울트라"]),
    ("Galaxy S25", "갤럭시 S25", 150_000, ["갤럭시 s25"]),
    ("Galaxy S25 Ultra", "갤럭시 S25 울트라", 150_000, ["갤럭시 s25 울트라"]),
    ("Galaxy S25+", "갤럭시 S25 플러스", 150_000, ["갤럭시 s25 플러스"]),
    ("Galaxy S25 Edge", "갤럭시 S25 엣지", 150_000, ["갤럭시 s25 엣지"]),
    ("Galaxy S26", "갤럭시 S26", 150_000, ["갤럭시 s26"]),
    ("Galaxy S26 Ultra", "갤럭시 S26 울트라", 150_000, ["갤럭시 s26 울트라"]),
    ("Galaxy S26+", "갤럭시 S26 플러스", 150_000, ["갤럭시 s26 플러스"]),
    ("Galaxy Z Flip7", "갤럭시 Z 플립7", 150_000, ["갤럭시 z 플립7"]),
    ("Galaxy Z Fold6", "갤럭시 Z 폴드6", 150_000, ["갤럭시 z 폴드6"]),
    ("Galaxy Z Fold7", "갤럭시 Z 폴드7", 150_000, ["갤럭시 z 폴드7"]),
    ("iPhone 15 Pro", "아이폰 15 프로", 150_000, ["아이폰 15 프로"]),
    ("iPhone 16", "아이폰 16", 150_000, ["아이폰 16"]),
    ("iPhone 16 Plus", "아이폰 16 플러스", 150_000, ["아이폰 16 플러스"]),
    ("iPhone 16 Pro", "아이폰 16 프로", 150_000, ["아이폰 16 프로"]),
    ("iPhone 17", "아이폰 17", 150_000, ["아이폰 17"]),
    ("iPhone 17 Pro", "아이폰 17 프로", 150_000, ["아이폰 17 프로"]),
    ("iPhone Air", "아이폰 에어", 150_000, ["아이폰 에어"]),
    ("Sony a6400", "소니 a6400", 150_000, ["소니 a6400"]),
    ("Sony a6700", "소니 a6700", 150_000, ["소니 a6700"]),
    ("Sony a7C II", "소니 a7c2", 150_000, ["소니 a7c2"]),
    ("Sony a7 IV", "소니 a7m4", 150_000, ["소니 a7m4"]),
    ("Canon R6 Mark II", "캐논 r6m2", 150_000, ["캐논 r6m2"]),
    ("Fujifilm X100V", "후지필름 X100V", 150_000, ["후지필름 x100v"]),
    ("Fujifilm X100VI", "후지 x100vi", 150_000, ["후지 x100vi"]),
    ("Ricoh GR III", "리코 gr3", 500_000, ["리코 gr3"]),
    ("Ricoh GR IIIx", "리코 gr3x", 500_000, ["리코 gr3x"]),
]


# SPECS에 없는 모델은 알림 대상이 아니므로 판매완료 평균만 계산한다(alert_keywords 없음).
CHART_ONLY_SEARCH_WORDS = {
    "RTX 5060": "RTX 5060",
    "RTX 3080": "RTX 3080",
    "RTX 3080 Ti": "RTX 3080 Ti",
    "RTX 5070": "RTX 5070",
    "RTX 4080": "RTX 4080",
    "RTX 5080": "RTX 5080",
    "RTX 3090": "RTX 3090",
    "RTX 4090": "RTX 4090",
    "RTX 5090": "RTX 5090",
    "Osmo Action 4": "오즈모 액션4",
    "Osmo Action 5 Pro": "오즈모 액션5 프로",
    "Osmo Action 6": "오즈모 액션6",
    "Osmo Pocket 3": "Osmo Pocket 3",
    "Osmo Pocket 4": "오즈모 포켓4",
    "Osmo Pocket 4P": "오즈모 포켓4p",
    "Galaxy S25 FE": "Galaxy S25 FE",
    "iPhone 17 Plus": "iPhone 17 Plus",
    "Sony FX3": "Sony FX3",
    "Sony a7 III": "소니 a7m3",
    "Sony a7 V": "소니 a7m5",
    "Sony a7CR": "Sony a7CR",
    "Sony a7R V": "소니 a7r5",
    "Sony a7R VI": "Sony a7R VI",
    "Panasonic GH7": "Panasonic GH7",
    "Panasonic S1R II": "Panasonic S1R II",
    "Panasonic S5 II": "Panasonic S5 II",
    "Panasonic S5 IIX": "Panasonic S5 IIX",
    "Panasonic S9": "Panasonic S9",
    "Insta360 Ace Pro 2": "Insta360 Ace Pro 2",
    "Insta360 GO 3S": "Insta360 GO 3S",
    "Insta360 GO Ultra": "Insta360 GO Ultra",
    "Canon PowerShot V1": "캐논 파워샷 v1",
    "Canon R1": "Canon R1",
    "Canon R10": "Canon R10",
    "Canon R3": "Canon R3",
    "Canon R5 Mark II": "Canon R5 Mark II",
    "Canon R6 Mark III": "Canon R6 Mark III",
    "Canon R7": "Canon R7",
    "Canon R8": "Canon R8",
    "Nikon Zf": "니콘 zf",
    "Fujifilm X-E5": "Fujifilm X-E5",
    "Fujifilm X-H2S": "Fujifilm X-H2S",
    "Fujifilm X-M5": "Fujifilm X-M5",
    "Fujifilm X-S20": "Fujifilm X-S20",
    "Fujifilm X-T5": "Fujifilm X-T5",
    "Fujifilm X-T50": "x-t50",
    "OM System TG-7": "OM SYSTEM TG-7",
    "GoPro MISSION 1": "GoPro MISSION 1",
    "GoPro MISSION 1 PRO": "GoPro MISSION 1 PRO",
    "GoPro HERO13 Black": "고프로 히어로13 블랙",
    "Galaxy S24": "갤럭시 S24",
    "Galaxy S24+": "갤럭시 S24 플러스",
    "Galaxy S24 FE": "갤럭시 S24 FE",
    "Galaxy S23+": "갤럭시 S23 플러스",
    "Galaxy S23 FE": "갤럭시 S23 FE",
    "Galaxy Z Flip6": "갤럭시 Z 플립6",
    "Galaxy Z Flip7 FE": "갤럭시 Z 플립7 FE",
    "Galaxy Z Flip5": "갤럭시 Z 플립5",
    "Galaxy Z Fold5": "갤럭시 Z 폴드5",
    "iPhone 15 Pro Max": "아이폰 15 프로 맥스",
    "iPhone 16 Pro Max": "아이폰 16 프로 맥스",
    "iPhone 17 Pro Max": "아이폰 17 프로 맥스",
    "iPhone 15": "아이폰 15",
    "iPhone 15 Plus": "아이폰 15 플러스",
    "iPhone 16e": "아이폰 16e",
    "iPhone 13": "아이폰 13",
    "iPhone 13 Pro": "아이폰 13 프로",
}


def chart_only_specs() -> list[tuple[str, str, int, list[str]]]:
    from normalize_mcp_refresh import minimum_price

    catalog = json.loads((ROOT / "data" / "catalog" / "products.json").read_text())["products"]
    first_product = {}
    for product in catalog:
        first_product.setdefault(product["model"], product)
    known = {spec[0] for spec in SPECS}
    return [
        (model, word, minimum_price(first_product[model]), [])
        for model, word in CHART_ONLY_SEARCH_WORDS.items()
        if model not in known
    ]


def fetch_prices(search_word: str) -> list[int]:
    body = json.dumps(
        {
            "searchWord": search_word,
            "productPriceSize": 1,
            "dateRange": WINDOW_DAYS,
            "priceType": 1,
        }
    ).encode()
    request = urllib.request.Request(
        API_URL, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    prices: list[int] = []
    for point in (payload.get("data", {}).get("productPrice") or {}).get("scatterPrices", []):
        for price_count in point.get("priceCounts", []):
            prices.extend([int(price_count["price"])] * int(price_count["count"]))
    return prices


def comparable_prices(prices: list[int], minimum: int) -> list[int]:
    candidates = [price for price in prices if price >= minimum]
    if not candidates:
        return []
    median = statistics.median(candidates)
    return [price for price in candidates if median * 0.5 <= price <= median * 1.75]


def alert_max_price(average: int) -> int:
    discounted = average * (100 - DISCOUNT_PERCENT) // 100
    return discounted // ROUNDING_KRW * ROUNDING_KRW


def main() -> None:
    parser = argparse.ArgumentParser(description="중고나라 판매가 차트로 최근 3개월 평균 갱신")
    parser.add_argument("--model", action="append", help="갱신할 모델. 생략하면 전체")
    args = parser.parse_args()
    all_specs = SPECS + chart_only_specs()
    specs = [spec for spec in all_specs if not args.model or spec[0] in args.model]
    unknown = set(args.model or []) - {spec[0] for spec in all_specs}
    if unknown:
        raise SystemExit(f"알 수 없는 모델: {', '.join(sorted(unknown))}")
    fetched_at = datetime.now(timezone.utc)
    output = AGGREGATES / f"sold-averages-{fetched_at.astimezone(KST).date().isoformat()}.json"
    rows = []
    for model, search_word, minimum, alert_keywords in specs:
        raw = fetch_prices(search_word)
        samples = comparable_prices(raw, minimum)
        average = round(sum(samples) / len(samples)) if samples else None
        rows.append(
            {
                "model": model,
                "search_word": search_word,
                "source_url": "https://web.joongna.com/search-price/"
                + urllib.parse.quote(search_word),
                "minimum_comparable_price_krw": minimum,
                "raw_sample_size": len(raw),
                "sample_size": len(samples),
                "average_price_krw": average,
                "alert_max_price_krw": alert_max_price(average) if average and alert_keywords else None,
                "alert_keywords": alert_keywords,
            }
        )
    payload = {
        "schema_version": 1,
        "fetched_at": fetched_at.isoformat(timespec="seconds"),
        "window_days": WINDOW_DAYS,
        "discount_percent": DISCOUNT_PERCENT,
        "rows": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"wrote {output.relative_to(ROOT)} ({len(rows)} models)")


if __name__ == "__main__":
    main()
