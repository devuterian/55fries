#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "catalog" / "products.json"
KST = timezone(timedelta(hours=9))

ALIASES = {
    "Osmo Action 4": ("osmoaction4", "오즈모액션4"),
    "Osmo Action 5 Pro": ("osmoaction5pro", "오즈모액션5프로"),
    "Osmo Action 6": ("osmoaction6", "오즈모액션6"),
    "Osmo Pocket 3": ("osmopocket3", "오즈모포켓3"),
    "Osmo Pocket 4": ("osmopocket4", "오즈모포켓4"),
    "Osmo Pocket 4P": ("osmopocket4p", "오즈모포켓4p"),
    "Galaxy Z Flip7": ("galaxyzflip7", "갤럭시z플립7", "갤럭시플립7", "zflip7"),
    "Galaxy Z Fold6": ("galaxyzfold6", "갤럭시z폴드6", "갤럭시폴드6", "zfold6"),
    "Galaxy Z Fold7": ("galaxyzfold7", "갤럭시z폴드7", "갤럭시폴드7", "zfold7"),
    "iPhone 15 Pro": ("iphone15pro", "아이폰15프로"),
    "iPhone 16": ("iphone16", "아이폰16"),
    "iPhone 16 Plus": ("iphone16plus", "아이폰16플러스"),
    "iPhone 16 Pro": ("iphone16pro", "아이폰16프로"),
    "iPhone 17": ("iphone17", "아이폰17"),
    "iPhone 17 Plus": ("iphone17plus", "아이폰17플러스"),
    "iPhone 17 Pro": ("iphone17pro", "아이폰17프로"),
    "iPhone Air": ("iphoneair", "아이폰에어"),
    "Sony FX3": ("sonyfx3", "소니fx3"),
    "Sony a6400": ("sonya6400", "소니a6400", "a6400"),
    "Sony a6700": ("sonya6700", "소니a6700", "a6700"),
    "Sony a7 III": ("sonya7iii", "소니a7iii", "a7iii", "a7m3", "a7mark3"),
    "Sony a7 IV": ("sonya7iv", "소니a7iv", "a7iv", "a7m4", "a7mark4"),
    "Sony a7 V": ("sonya7v", "소니a7v", "a7v", "a7m5", "a7mark5"),
    "Sony a7C II": ("sonya7cii", "소니a7cii", "a7cii", "a7c2"),
    "Sony a7CR": ("sonya7cr", "소니a7cr", "a7cr"),
    "Sony a7R V": ("sonya7rv", "소니a7rv", "a7rv", "a7r5"),
    "Sony a7R VI": ("sonya7rvi", "소니a7rvi", "a7rvi", "a7r6"),
    "Panasonic GH7": ("panasonicgh7", "파나소닉gh7", "lumixgh7", "루믹스gh7", "gh7"),
    "Panasonic S1R II": ("panasonics1rii", "파나소닉s1rii", "lumixs1rii", "s1r2"),
    "Panasonic S5 II": ("panasonics5ii", "파나소닉s5ii", "lumixs5ii", "s5ii", "s5m2"),
    "Panasonic S5 IIX": ("panasonics5iix", "파나소닉s5iix", "lumixs5iix", "s5iix", "s5m2x"),
    "Panasonic S9": ("panasonics9", "파나소닉s9", "lumixs9", "루믹스s9"),
    "Insta360 Ace Pro 2": ("insta360acepro2", "인스타360acepro2", "에이스프로2"),
    "Insta360 GO 3S": ("insta360go3s", "인스타360go3s", "go3s"),
    "Insta360 GO Ultra": ("insta360goultra", "인스타360고울트라", "goultra"),
    "Canon PowerShot V1": ("canonpowershotv1", "캐논powershotv1", "캐논파워샷v1", "powershotv1"),
    "Canon R1": ("canonr1", "캐논r1"),
    "Canon R10": ("canonr10", "캐논r10"),
    "Canon R3": ("canonr3", "캐논r3"),
    "Canon R5 Mark II": ("canonr5markii", "캐논r5markii", "캐논r5m2", "eosr5markii", "r5m2"),
    "Canon R6 Mark II": ("canonr6markii", "캐논r6markii", "캐논r6m2", "eosr6markii", "r6m2"),
    "Canon R6 Mark III": ("canonr6markiii", "캐논r6markiii", "캐논r6m3", "eosr6markiii", "r6m3"),
    "Canon R7": ("canonr7", "캐논r7"),
    "Canon R8": ("canonr8", "캐논r8"),
    "Nikon Zf": ("nikonzf", "니콘zf"),
    "Fujifilm X-E5": ("fujifilmxe5", "후지필름xe5", "후지xe5", "xe5"),
    "Fujifilm X-H2S": ("fujifilmxh2s", "후지필름xh2s", "후지xh2s", "xh2s"),
    "Fujifilm X-M5": ("fujifilmxm5", "후지필름xm5", "후지xm5", "xm5"),
    "Fujifilm X-S20": ("fujifilmxs20", "후지필름xs20", "후지xs20", "xs20"),
    "Fujifilm X-T5": ("fujifilmxt5", "후지필름xt5", "후지xt5", "xt5"),
    "Fujifilm X-T50": ("fujifilmxt50", "후지필름xt50", "후지xt50", "xt50"),
    "Fujifilm X100V": ("fujifilmx100v", "후지필름x100v", "후지x100v", "x100v"),
    "Fujifilm X100VI": ("fujifilmx100vi", "후지필름x100vi", "후지x100vi", "x100vi"),
    "Ricoh GR III": ("ricohgriii", "리코griii", "gr3"),
    "Ricoh GR IIIx": ("ricohgriiix", "리코griiix", "gr3x"),
    "Ricoh GR IV": ("ricohgriv", "리코griv", "리코gr4", "gr4"),
    "Sony RX100 VII": ("sonyrx100vii", "소니rx100vii", "rx100vii", "rx100m7"),
    "Panasonic TZ99 / ZS99": ("panasonictz99", "panasoniczs99", "lumixtz99", "lumixzs99", "루믹스tz99", "루믹스zs99"),
    "OM System TG-7": ("omsystemtg7", "올림푸스tg7", "toughtg7", "tg7"),
    "GoPro MISSION 1": ("gopromission1", "고프로미션1", "mission1"),
    "GoPro MISSION 1 PRO": ("gopromission1pro", "고프로미션1프로", "mission1pro"),
    "GoPro HERO13 Black": ("goprohero13black", "고프로히어로13블랙", "고프로13블랙", "hero13black"),
    "Insta360 X6": ("insta360x6", "인스타360x6"),
    "DJI Mini 5 Pro": ("djimini5pro", "dji미니5프로", "미니5프로"),
    "DJI Air 3S": ("djiair3s", "dji에어3s", "에어3s"),
    "DJI Mavic 4 Pro": ("djimavic4pro", "dji매빅4프로", "매빅4프로"),
    "iPhone 14 Pro": ("iphone14pro", "아이폰14프로"),
    "iPhone 14 Pro Max": ("iphone14promax", "아이폰14프맥", "아이폰14pm", "아이폰14프로맥스"),
    "MacBook Air M4": ("macbookairm4", "맥북에어m4"),
    "MacBook Pro M4 Pro": ("macbookprom4pro", "맥북프로m4pro", "맥북프로m4프로"),
    "MacBook Pro M4 Max": ("macbookprom4max", "맥북프로m4max", "맥북프로m4맥스"),
    "Apple Watch Series 10": ("applewatchseries10", "applewatch10", "애플워치시리즈10", "애플워치10"),
    "Apple Watch Ultra 2": ("applewatchultra2", "애플워치울트라2"),
    "Galaxy Z Flip6": ("galaxyzflip6", "갤럭시z플립6", "갤럭시플립6", "zflip6"),
    "Galaxy Z Flip7 FE": ("galaxyzflip7fe", "갤럭시z플립7fe", "갤럭시플립7fe", "zflip7fe", "플립7fe"),
    "Galaxy Z Flip5": ("galaxyzflip5", "갤럭시z플립5", "갤럭시플립5", "zflip5"),
    "Galaxy Z Fold5": ("galaxyzfold5", "갤럭시z폴드5", "갤럭시폴드5", "zfold5"),
    "iPhone 15 Pro Max": ("iphone15promax", "아이폰15프맥", "아이폰15pm", "아이폰15프로맥스", "아이폰15promax"),
    "iPhone 16 Pro Max": ("iphone16promax", "아이폰16프맥", "아이폰16pm", "아이폰16프로맥스", "아이폰16promax"),
    "iPhone 17 Pro Max": ("iphone17promax", "아이폰17프맥", "아이폰17pm", "아이폰17프로맥스", "아이폰17promax"),
    "iPhone 15": ("iphone15", "아이폰15"),
    "iPhone 15 Plus": ("iphone15plus", "아이폰15플러스", "아이폰15plus"),
    "iPhone 16e": ("iphone16e", "아이폰16e"),
    "iPhone 13": ("iphone13", "아이폰13"),
    "iPhone 13 Pro": ("iphone13pro", "아이폰13프로", "아이폰13pro"),
}

# 고장 계열(DEFECT)은 버리지 않고 모델마다 "고장·파손" 칸으로 모은다. 여기는 매물이 아니거나 본체가 아닌 글이다.
BLOCKED = re.compile(
    r"삽니다|구매합니다|구해요|매입|최고가|대여|렌탈|교환원함|"
    r"박스만|박스\s*단품|케이스|필름|보호유리|"
    r"배터리\s*(단품|만)|충전기\s*(단품|만)|스트랩|마운트|커버|모형|목업|"
    r"완본체|데스크탑|게이밍\s*(컴퓨터|pc)|조립\s*pc|교환|"
    r"케이지|뷰파인더|메인보드|lcd\s*멍|액정\s*멍|레노버|리전\d|레이저\s*블레이드",
    re.IGNORECASE,
)

DEFECT_VARIANT = "고장·파손"
UNKNOWN_CAPACITY_VARIANT = "용량 미확인"
CAPACITIES = {"128GB", "256GB", "512GB", "1TB", "2TB"}
DEFECT_MIN_PRICE_KRW = 100_000
DEFECT = re.compile(
    r"부품용|수리용|고장|파손|액정\s*(?:불량|깨짐|깨졌)|화면\s*깨|(?<!무)번인|(?<!무)잔상|"
    r"터치\s*(?:불가|불량|안\s*됨)|침수|페이스\s*아이디\s*(?:불량|불가|안\s*됨)|lcd\s*멍|액정\s*멍",
    re.IGNORECASE,
)
# 본문은 업자 안내문("파손 시 환불 불가", "침수폰 취급 안 함")과 부정("잔상 없음", "무잔상")이 흔하다.
# 문장 단위로 보고, 안내·조건·부정 표현이 섞인 문장은 이 매물의 상태로 보지 않는다.
BODY_DEFECT = re.compile(
    r"부품용|수리용|(?<!잔)고장|파손|깨짐|깨져|깨졌|실금|(?<!무)잔상|(?<!무)번인|침수|"
    r"터치\s*(?:불가|불량|안\s*됨)|페이스\s*아이디\s*(?:불량|불가|안\s*됨)|lcd\s*멍|액정\s*멍",
    re.IGNORECASE,
)
BODY_NOT_ABOUT_ITEM = re.compile(
    r"a/?s|면책|환불|반품|교환|보상|보증|과실|부주의|매입|구매|취급|않|없|無|❌|일절|전혀|테스트|등급|"
    r"급\s*[:：]|있거나|이력|여부|경우|※|[^a-z]x(?![a-z])|노\s*(?:잔상|번인|파손)|픽셀|[:：]\s*무",
    re.IGNORECASE,
)
BODY_SENTENCE = re.compile(r"[\n.!?]|\s{2,}")
BODY_CAPACITY = re.compile(r"(?<!\d)(?:128|256|512)\s*(?:gb|기가|g)(?![a-z0-9])|(?<!\d)[12]\s*(?:tb|테라)(?![a-z0-9])", re.IGNORECASE)


def mentions_defect(text: str, body: bool = False) -> bool:
    if not body:
        return bool(DEFECT.search(text))
    return any(
        BODY_DEFECT.search(sentence) and not BODY_NOT_ABOUT_ITEM.search(sentence)
        for sentence in BODY_SENTENCE.split(text)
    )


def body_capacity(description: str) -> str | None:
    """본문에 용량이 한 가지만 적혀 있을 때만 믿는다. 여러 개면 업자 재고 목록일 수 있다."""
    found = {capacity(match.group(0)) for match in BODY_CAPACITY.finditer(description)}
    found.discard(None)
    return found.pop() if len(found) == 1 else None


def compact(value: str) -> str:
    return re.sub(r"[^0-9a-z가-힣+]", "", value.casefold())


def model_matches(model: str, title: str) -> bool:
    text = compact(title)
    if model.startswith("RTX "):
        number = re.search(r"\d{4}", model).group()
        if f"rtx{number}" not in text:
            return False
        return ("ti" in model.casefold()) == ("ti" in text)
    if model.startswith("Galaxy S"):
        number = re.search(r"s\d+", model.casefold()).group()
        if number not in text or not ("galaxy" in text or "갤럭시" in text):
            return False
        suffixes = {"Ultra": ("ultra", "울트라", f"{number}u"), "Edge": ("edge", "엣지"), "FE": ("fe",), "+": ("+", "plus", "플러스")}
        wanted = next((key for key in suffixes if key in model), None)
        present = next((key for key, words in suffixes.items() if any(word in text for word in words)), None)
        return wanted == present
    if model.startswith("iPhone ") and "Pro Max" not in model:
        number = re.search(r"\d+", model)
        # "아이폰16 프맥", "16pm"은 Pro Max 약칭이다.
        if number and re.search(rf"(?<!\d){number.group()}(?:프맥|pm(?![a-z]))", text):
            return False
    aliases = ALIASES.get(model, (compact(model),))
    if not any(alias in text for alias in aliases):
        return False
    conflicts = {
        "Osmo Pocket 4": ("pocket4p", "포켓4p"),
        "iPhone 16": ("iphone16pro", "아이폰16프로", "아이폰16pro", "iphone16plus", "아이폰16플러스", "아이폰16plus", "iphone16e", "아이폰16e"),
        "iPhone 15 Pro": ("iphone15promax", "아이폰15프로맥스", "아이폰15promax", "15프맥", "15pm"),
        "iPhone 16 Pro": ("iphone16promax", "아이폰16프로맥스", "아이폰16promax", "16프맥", "16pm"),
        "iPhone 17": ("iphone17pro", "아이폰17프로", "아이폰17pro", "iphone17plus", "아이폰17플러스", "아이폰17plus", "iphone17e", "아이폰17e"),
        "iPhone 17 Pro": ("iphone17promax", "아이폰17프로맥스", "아이폰17promax", "17프맥", "17pm"),
        "Canon PowerShot V1": ("powershotv10", "파워샷v10"),
        "Canon R1": ("canonr10", "캐논r10"),
        "Nikon Zf": ("nikonzfc", "니콘zfc"),
        "Sony FX3": ("fx30",),
        "Fujifilm X-E5": ("xe4",),
        "Fujifilm X-M5": ("xt30",),
        "Sony a7 III": ("a7rii", "a7riii"),
        "Sony a7 IV": ("a7riv",),
        "Panasonic S5 II": ("s5iix", "s5m2x"),
        "Fujifilm X100V": ("x100vi",),
        "Ricoh GR III": ("griiix", "gr3x"),
        "Ricoh GR IV": ("grivhdf", "gr4hdf", "grii", "gr3"),
        "GoPro MISSION 1": ("mission1pro",),
        "iPhone 14 Pro": ("iphone14promax", "아이폰14프로맥스", "아이폰14promax", "14프맥", "14pm"),
        "MacBook Air M4": ("macbookprom4", "맥북프로m4"),
        "MacBook Pro M4 Pro": ("m4max", "m4맥스"),
        "MacBook Pro M4 Max": ("m4pro", "m4프로"),
        "Apple Watch Series 10": ("ultra", "울트라"),
        "Galaxy Z Flip7": ("flip7fe", "플립7fe"),
        "iPhone 15": ("iphone15pro", "아이폰15프로", "아이폰15pro", "iphone15plus", "아이폰15플러스", "아이폰15plus"),
        "iPhone 13": ("iphone13pro", "아이폰13프로", "아이폰13pro", "iphone13mini", "아이폰13미니", "아이폰13mini"),
        "iPhone 13 Pro": ("iphone13promax", "아이폰13프로맥스", "아이폰13promax", "13프맥", "13pm"),
    }
    if model == "Fujifilm X100VI" and re.search(r"x100v(?!i)", text):
        return False
    if model == "Sony a7C II" and re.search(r"a7c(?!2|ii|r)", text):
        return False
    return not any(word in text for word in conflicts.get(model, ()))


def capacity(title: str) -> str | None:
    text = title.casefold()
    match = re.search(r"(?<!\d)([12])\s*(?:tb|테라|t)(?![a-z0-9])", text)
    if match:
        return f"{match.group(1)}TB"
    match = re.search(r"(?<!\d)(128|256|512)\s*(?:gb|기가|g)?(?!\d)", text)
    return f"{match.group(1)}GB" if match else None


def choose_variant(model: str, variants: list[str], title: str) -> str | None:
    if all(value in {"128GB", "256GB", "512GB", "1TB", "2TB"} for value in variants):
        found = capacity(title)
        if found is None and len(variants) == 1:
            return variants[0]
        return found if found in variants else None
    if model == "RTX 3080":
        text = compact(title)
        if "12gb" in text or "12g" in text:
            return "12GB"
        if "10gb" in text or "10g" in text or not re.search(r"(?:8|16|20|24)g(?:b)?", text):
            return "10GB"
        return None
    if len(variants) == 1:
        return variants[0]
    text = compact(title)
    if model.startswith("Osmo Action"):
        if "어드벤처" in text or "어드밴처" in text or "adventure" in text:
            return "어드벤처"
        if "강화" in text:
            return "강화"
        return "스탠다드/본체"
    if model.startswith("Osmo Pocket"):
        if "크리에이터" in text or "creator" in text:
            return "크리에이터"
        if "브이로그" in text or "vlog" in text or "풀세트" in text or "세트" in text:
            return "브이로그/세트"
        return "스탠다드"
    if model.startswith("DJI ") and set(variants) == {"스탠다드", "플라이 모어"}:
        return "플라이 모어" if re.search(r"플라이\s*모어|fly\s*more|콤보|combo", title, re.IGNORECASE) else "스탠다드"
    if model.startswith("MacBook"):
        text = compact(title)
        for size in ("13", "14", "15", "16"):
            if size in text and f"{size}인치" in variants:
                return f"{size}인치"
        return None
    if model == "Apple Watch Series 10":
        text = compact(title)
        size = next((value for value in ("42", "46") if value in text), None)
        if not size:
            return None
        network = "Cellular" if any(value in text for value in ("cellular", "셀룰러", "lte")) else "GPS"
        variant = f"{size}mm {network}"
        return variant if variant in variants else None
    return variants[0]


def minimum_price(product: dict) -> int:
    if product["variant"] == DEFECT_VARIANT:
        return DEFECT_MIN_PRICE_KRW
    model = product["model"]
    if model.startswith("RTX "):
        return {
            "RTX 3080": 300_000, "RTX 3080 Ti": 400_000, "RTX 3090": 500_000,
            "RTX 4080": 800_000, "RTX 4090": 1_500_000, "RTX 5060": 300_000,
            "RTX 5070": 600_000, "RTX 5080": 1_200_000, "RTX 5090": 2_000_000,
        }[model]
    if model.startswith("MacBook"):
        return 700_000
    if model.startswith("DJI Mini"):
        return 500_000
    if model.startswith("DJI Air"):
        return 700_000
    if model.startswith("DJI Mavic"):
        return 1_500_000
    if model in {"Ricoh GR IV", "Sony RX100 VII"}:
        return 500_000
    if model in {"Panasonic TZ99 / ZS99", "OM System TG-7", "Insta360 X6"}:
        return 300_000
    if model.startswith("GoPro MISSION"):
        return 350_000
    if model == "GoPro HERO13 Black":
        return 200_000
    return {
        "NVIDIA": 150_000,
        "DJI": 100_000,
        "Samsung": 150_000,
        "Apple": 150_000,
        "Insta360": 80_000,
    }.get(product["brand"], 150_000)


def comparable(product: dict, title: str, description: str | None, price: int) -> bool:
    if price < minimum_price(product) or BLOCKED.search(title):
        return False
    if product["model"].startswith("RTX "):
        details = f"{title}\n{description or ''}"
        if re.search(r"노트북|노트북용|게이밍\s*노트|랩탑|laptop|notebook|mobile\s*gpu", details, re.IGNORECASE):
            return False
        expected = re.fullmatch(r"(\d{1,2})GB", product["variant"], re.IGNORECASE)
        mentioned = {
            int(value)
            for value in re.findall(r"(?<!\d)(\d{1,2})\s*(?:GB|G)(?![A-Za-z])", title, re.IGNORECASE)
        }
        if expected and mentioned and int(expected.group(1)) not in mentioned:
            return False
    if product["model"] == "Ricoh GR III" and "hdf" in title.casefold():
        return False
    if product["brand"] == "Insta360" and re.search(r"렌즈|그립", title) and not re.search(r"본체|카메라", title):
        return False
    if product["variant"] in {"Body", "바디", "본체", "일반형"} and re.search(
        r"렌즈|\d{2,3}[-~]\d{2,3}|\d+\s*(mm|미리)|올인원\s*세트", title, re.IGNORECASE
    ):
        return False
    return True



def title_model(title: str, models: list[str]) -> str | None:
    """검색어와 다른 모델 글(예: "아이폰 16" 검색에 나온 16 프로)은 버리지 않고 맞는 모델로 옮긴다."""
    hits = sorted((model for model in models if model_matches(model, title)), key=len, reverse=True)
    if not hits or (len(hits) > 1 and len(hits[0]) == len(hits[1])):
        return None
    return hits[0]


def classify(
    query_model: str, title: str, description: str | None, price: int,
    products_by_model: dict[str, list[dict]],
) -> dict | None:
    model = query_model if model_matches(query_model, title) else title_model(title, list(products_by_model))
    if model is None or BLOCKED.search(title):
        return None
    by_variant = {product["variant"]: product for product in products_by_model[model]}
    if mentions_defect(title) or (description and mentions_defect(description, body=True)):
        product = by_variant.get(DEFECT_VARIANT)
    else:
        variants = [value for value in by_variant if value not in {DEFECT_VARIANT, UNKNOWN_CAPACITY_VARIANT}]
        variant = choose_variant(model, variants, title)
        if variant is None and description and all(value in CAPACITIES for value in variants):
            found = body_capacity(description)
            variant = found if found in variants else None
        if variant is None and UNKNOWN_CAPACITY_VARIANT in by_variant:
            variant = UNKNOWN_CAPACITY_VARIANT
        product = by_variant.get(variant)
    if product is None or not comparable(product, title, description, price):
        return None
    return product


def record(product: dict, marketplace: str, item: dict, state: str, fetched_at: str) -> dict:
    timestamp = item.get("updated_at") if marketplace == "bunjang" else item.get("sorted_at")
    external_id = item.get("product_id") if marketplace == "bunjang" else item.get("sequence")
    result = {
        "marketplace": marketplace,
        "external_listing_id": str(external_id),
        "brand": product["brand"],
        "model": product["model"],
        "variant": product["variant"],
        "seller_external_id": str(item["seller_id"]) if item.get("seller_id") is not None else None,
        "seller_name": item.get("seller_name"),
        "title": item["title"],
        "listing_url": item["listing_url"],
        "price_krw": int(item["price_krw"]),
        "state": state,
        "listed_at": None,
        "updated_at": timestamp if state == "active" else None,
        "sold_at": timestamp if state == "sold" else None,
        "is_comparable": True,
        "exclusion_reason": None,
        "raw": {"source_fetched_at": fetched_at, "source_item": item},
    }
    return result


def kst_source_date(value: str | None) -> str | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST).isoformat(timespec="seconds")


def record_v2(product: dict, item: dict, fetched_at: str, state: str = "active") -> dict:
    if item["marketplace"] == "joongna":
        updated_at = item.get("updated_at") or kst_source_date((item.get("source_dates") or {}).get("sortDate"))
    else:
        updated_at = item.get("updated_at")
    return {
        "marketplace": item["marketplace"],
        "external_listing_id": str(item["listing_id"]),
        "brand": product["brand"],
        "model": product["model"],
        "variant": product["variant"],
        "seller_external_id": str(item["seller_id"]) if item.get("seller_id") is not None else None,
        "seller_name": item.get("seller_name"),
        "title": item["title"],
        "listing_url": item["listing_url"],
        "price_krw": int(item["price_krw"]),
        "state": state,
        "listed_at": None,
        # 판매완료는 판매 시각을 따로 주지 않아 마지막 수정(등록) 시각으로 근사한다.
        "updated_at": updated_at if state == "active" else None,
        "sold_at": updated_at if state == "sold" else None,
        "is_comparable": True,
        "exclusion_reason": None,
        "raw": {"source_fetched_at": fetched_at, "source_item": item},
    }


def safety_v2(item: dict, listing_url: str, fetched_at: str) -> dict:
    evidence = item.get("seller_evidence") or {}
    count = evidence.get("safe_trade_count") or {}
    verified = evidence.get("status") == "available" and count.get("status") == "available" and count.get("value") is not None
    if verified:
        raw = {"source_metrics": evidence.get("source_metrics"), "source_field": count.get("source_field")}
    elif item["marketplace"] == "bunjang":
        raw = {"reason": "번개장터 MCP는 판매 횟수만 주고 안전거래 횟수와 같다고 보장하지 않음", "source_metrics": evidence.get("source_metrics")}
    else:
        raw = {"reason": "MCP 응답에 판매자의 안전거래 횟수가 없음", "seller_error": item.get("seller_error")}
    return {
        "marketplace": item["marketplace"],
        "seller_external_id": str(item["seller_id"]),
        "checked_at": evidence.get("checked_at") or item.get("seller_checked_at") or fetched_at,
        "verification_status": "verified" if verified else "unavailable",
        "safe_trade_count": int(count["value"]) if verified else None,
        "source_url": listing_url,
        "raw": raw,
    }


def normalize_v2(raw: dict, catalog: dict) -> dict:
    products_by_model: dict[str, list[dict]] = {}
    for product in catalog["products"]:
        products_by_model.setdefault(product["model"], []).append(product)
    output: dict[tuple[str, str], dict] = {}
    safety: dict[tuple[str, str], dict] = {}
    for query in raw["queries"]:
        products = products_by_model[query["model"]]
        variants = [product["variant"] for product in products]
        for marketplace in ("joongna", "bunjang"):
            response = query[marketplace]["response"]
            fetched_at = response.get("page_observed_at") or raw["fetched_at"]
            for item in response.get("listings") or []:
                if item.get("status") != "on_sale":
                    continue
                title = item.get("title") or ""
                if not model_matches(query["model"], title):
                    continue
                variant = choose_variant(query["model"], variants, title)
                product = next((value for value in products if value["variant"] == variant), None)
                if not product or not comparable(product, title, item.get("description"), int(item.get("price_krw") or 0)):
                    continue
                normalized = record_v2(product, item, fetched_at)
                key = (marketplace, normalized["external_listing_id"])
                output.setdefault(key, normalized)
                if normalized["seller_external_id"]:
                    safety[(marketplace, normalized["seller_external_id"])] = safety_v2(item, normalized["listing_url"], fetched_at)
            sold_response = ((query.get("sold") or {}).get(marketplace) or {}).get("response") or {}
            for item in sold_response.get("listings") or []:
                if item.get("status") != "sold":
                    continue
                title = item.get("title") or ""
                if not model_matches(query["model"], title):
                    continue
                variant = choose_variant(query["model"], variants, title)
                product = next((value for value in products if value["variant"] == variant), None)
                if not product or not comparable(product, title, item.get("description"), int(item.get("price_krw") or 0)):
                    continue
                normalized = record_v2(product, item, sold_response.get("page_observed_at") or raw["fetched_at"], "sold")
                if normalized["sold_at"]:
                    output.setdefault((marketplace, normalized["external_listing_id"]), normalized)
    return {
        "run_id": raw["run_id"],
        "fetched_at": datetime.fromisoformat(raw["fetched_at"].replace("Z", "+00:00")).astimezone(KST).isoformat(timespec="seconds"),
        "listings": sorted(output.values(), key=lambda item: (item["brand"], item["model"], item["variant"], item["marketplace"], item["external_listing_id"])),
        "seller_safety_checks": sorted(safety.values(), key=lambda item: (item["marketplace"], item["seller_external_id"])),
        "quality_issues": [],
    }


def normalize(raw: dict, catalog: dict, descriptions: dict[tuple[str, str], str] | None = None) -> dict:
    if raw.get("schema_version") == 2:
        return normalize_v2(raw, catalog)
    normalized_fetched_at = datetime.fromisoformat(raw["fetched_at"].replace("Z", "+00:00")).astimezone(KST).isoformat(timespec="seconds")
    products_by_model: dict[str, list[dict]] = {}
    for product in catalog["products"]:
        products_by_model.setdefault(product["model"], []).append(product)
    output: dict[tuple[str, str], dict] = {}
    safety: dict[tuple[str, str], dict] = {}
    quality_issues: list[dict] = []
    for query in raw["queries"]:
        available = query["joongna"].get("available_listings") or []
        sold = (query["joongna"].get("sold_price_history") or {}).get("listings") or []
        active_ids = {str(item["sequence"]) for item in available if item.get("sequence") is not None}
        sold_ids = {str(item["sequence"]) for item in sold if item.get("sequence") is not None}
        overlapping_ids = active_ids & sold_ids
        if overlapping_ids:
            quality_issues.append(
                {
                    "model": query["model"],
                    "code": "joongna_active_sold_overlap",
                    "active_count": len(active_ids),
                    "sold_count": len(sold_ids),
                    "overlap_count": len(overlapping_ids),
                    "action": "overlapping_sold_listings_excluded",
                }
            )
        datasets = [
            ("joongna", "active", available, query["joongna"].get("fetched_at")),
            (
                "joongna",
                "sold",
                [item for item in sold if str(item.get("sequence")) not in overlapping_ids],
                query["joongna"].get("fetched_at"),
            ),
            ("bunjang", "active", query["bunjang"].get("listings") or [], query["bunjang"].get("fetched_at")),
        ]
        for marketplace, state, items, source_fetched_at in datasets:
            for item in items:
                title = item.get("title") or ""
                external_id = str(item.get("product_id") if marketplace == "bunjang" else item.get("sequence"))
                description = descriptions.get((marketplace, external_id)) if descriptions else None
                product = classify(
                    query["model"], title, description or item.get("description"),
                    int(item.get("price_krw") or 0), products_by_model,
                )
                if not product:
                    continue
                normalized = record(product, marketplace, item, state, source_fetched_at or raw["fetched_at"])
                normalized["raw"]["description_checked"] = description is not None
                key = (marketplace, normalized["external_listing_id"])
                if key not in output:
                    output[key] = normalized
                seller_id = normalized["seller_external_id"]
                if seller_id:
                    safety[(marketplace, seller_id)] = {
                        "marketplace": marketplace,
                        "seller_external_id": seller_id,
                        "checked_at": source_fetched_at or raw["fetched_at"],
                        "verification_status": "unavailable",
                        "safe_trade_count": None,
                        "source_url": normalized["listing_url"],
                        "raw": {"reason": "MCP 응답에 판매자의 안전거래 횟수가 없음"},
                    }
    return {
        "run_id": raw["run_id"],
        "fetched_at": normalized_fetched_at,
        "listings": sorted(output.values(), key=lambda item: (item["brand"], item["model"], item["variant"], item["marketplace"], item["external_listing_id"])),
        "seller_safety_checks": sorted(safety.values(), key=lambda item: (item["marketplace"], item["seller_external_id"])),
        "quality_issues": quality_issues,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP 원본을 살만한가 매물 스키마로 정규화")
    parser.add_argument("raw", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = normalize(json.loads(args.raw.read_text()), json.loads(CATALOG.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(f"normalized listings: {len(payload['listings'])}")
    print(f"seller safety checks: {len(payload['seller_safety_checks'])}")


if __name__ == "__main__":
    main()
