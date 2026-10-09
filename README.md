# 55FRIES

중고 기기의 현재가와 기간 통계를 근거 매물 링크와 함께 관리하는 가격 가이드입니다. 화면에서는 `판매중 최저가 → 6개월 최저 → 3개월 평균`을 보여주고, `판매중-안전` 값과 주의 판정은 JSON·DB에 그대로 보존합니다.

현재 공개 사이트: https://devuterian.github.io/salmanhanga/

**JSON과 JSON Schema가 원본**입니다. SQLite는 JSON 원본을 빠르게 검색하고 가격표를 계산하기 위해 재생성하는 로컬 캐시입니다.

## 핵심 규칙

- 판매중 가격은 게시·갱신일이 기준 시각에서 **25일 이내**인 정상 매물만 사용합니다.
- 안전거래 0회인 판매자는 `주의 · 안전거래 0회`로 표시합니다.
- 안전거래 이력을 확인할 수 없는 판매자는 `주의 · 안전거래 이력 확인불가`로 표시합니다.
- 안전거래 이력이 확인되고 1회 이상인 판매자 중 최저가를 `판매중-안전`에 표시합니다.
- `가격 매력도`는 판매중 최저가를 최근 3개월 판매완료 평균과 비교해 `아주 쌈`부터 `많이 비쌈`까지 표시합니다.
- 3개월 평균은 중고나라 `판매가(EXECUTION)` 시계열의 최근 90일 표본에서 모델별 최소 정상가와 이상값을 제외한 산술평균입니다.
- 3개월 표본이 5건보다 적으면 `표본 적음`을 함께 표시하고, 평균이나 현재가가 없으면 판단하지 않습니다.
- 모든 가격 근거에는 중고나라 또는 번개장터 원문 링크를 저장합니다.
- 판매중 목록과 ID가 겹치는 `판매가` 응답은 판매완료 표본으로 쓰지 않고 `quality_issues`에 기록합니다.
- 기존 2026-09-20 데이터는 원형 그대로 보존합니다. 부족한 날짜나 판매자 이력을 추측해 채우지 않습니다.

## 저장소 구조

```text
config/             JSON으로 관리하는 가격 계산 규칙
data/catalog/       JSON 상품 카탈로그
data/raw/           MCP가 돌려준 원본 JSON
data/imports/       정규화한 매물·레거시 수집 스냅샷
db/migrations/      재현 가능한 SQLite 스키마
docs/               데이터 모델과 판정 기준
schemas/            수집·안전거래·출력 JSON 계약
scripts/            DB 초기화, 수집 반영, 계산, 사이트 빌드
src/                사이트 원본
dist/               ChatGPT Sites에 배포할 정적 결과
tests/              25일·주의·판매중-안전 회귀 테스트
var/                로컬 SQLite DB. Git에는 올리지 않음
```

## 시작하기

Python 3.11 이상이 필요합니다. JSON Schema 검증 도구는 개발 의존성으로 분리했습니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
make PYTHON=.venv/bin/python bootstrap
make PYTHON=.venv/bin/python test
make PYTHON=.venv/bin/python verify
```

`make bootstrap`은 마이그레이션과 모든 수집 스냅샷으로 `var/salmanhanga.sqlite`를 다시 만듭니다. DB 파일은 결과물이므로 커밋하지 않습니다.

## 새 MCP 수집 반영

중고나라·번개장터 원격 MCP로 모델마다 판매중 매물을 한 번씩 받아 `data/raw/`에 모읍니다.

1. 모델마다 두 도구를 호출합니다. 파라미터는 원본 파일의 `params`에 그대로 남깁니다.
   - `joongna_search_keyword`: `statuses=["on_sale"]`, `min_price_krw`, `include_details=false`, `include_seller_evidence=true`
   - `bunjang_search`: 같은 조건에서 `include_seller_evidence`만 뺍니다.
   - `min_price_krw`는 `scripts/normalize_mcp_refresh.py`의 `minimum_price()`와 같은 값입니다. 잡매물이 줄어 응답이 작아집니다.
   - 모델 이름이 한글 검색어로 더 잘 잡히면(`소니 a7m4` 등) 그 검색어를 씁니다. 한 모델에 검색어가 여럿이면 `queries`에 같은 모델을 여러 번 넣습니다.
2. 응답을 `schema_version: 2` 형식으로 `data/raw/mcp-full-refresh-YYYY-MM-DD.json`에 저장하고 스키마로 검사합니다. 용량 때문에 `image_urls`·`thumbnail_url`만 뺍니다.
3. 3개월 평균은 MCP가 아니라 중고나라 가격 차트 API로 따로 받습니다.
4. 정규화하고 DB와 사이트를 다시 만듭니다.

```bash
.venv/bin/python scripts/refresh_sold_averages.py          # 전체. --model "Sony a7 IV"처럼 골라도 됨
.venv/bin/python scripts/validate_json.py
.venv/bin/python scripts/normalize_mcp_refresh.py \
  data/raw/mcp-full-refresh-2026-10-09.json \
  data/imports/mcp-full-refresh-2026-10-09.json
make PYTHON=.venv/bin/python bootstrap
make PYTHON=.venv/bin/python build
make PYTHON=.venv/bin/python test
make PYTHON=.venv/bin/python verify
```

### 2026-10-09 수집부터 달라진 점

- **판매자 안전거래 횟수**: 중고나라는 `joongna_search_keyword`의 `include_seller_evidence`로 받아 `판매중-안전`을 채웁니다. 번개장터는 판매 횟수(`salesCount`)만 주고 안전거래 횟수와 같다는 보장이 없어서 계속 `주의 · 안전거래 이력 확인불가`입니다.
- **기준일 당일 수집분만 현재가에 씁니다.** 이전 날짜 수집에서 본 매물은 지금 팔렸는지 알 수 없어서 쓰지 않습니다.
- **3개월 평균**은 중고나라 판매가 차트 기준이고 모델 전체 구성이 섞입니다. 개별 매물 링크가 없다고 비고에 적습니다. 차트 검색어가 안 잡히는 모델은 `표본 미확보`입니다.
- **6개월 최저**는 판매완료 매물 링크가 있어야 하는데 이번 수집에는 판매완료 검색이 없어서 전부 `표본 미확보`입니다.
- 검색은 첫 페이지(최근순 50/60건)만 봅니다. 매물이 많은 모델은 일부만 보일 수 있습니다.

### 2026-09-20 수집(이전 형식, `schema_version: 1`)

현재 MCP는 판매자의 안전거래 횟수를 주지 않습니다. 그래서 해당 판매자는 모두 `주의 · 안전거래 이력 확인불가`로 표시하고 `판매중-안전`에는 넣지 않습니다. 중고나라의 판매 이력 목록도 이번 수집에서는 판매중 목록과 동일하게 내려왔습니다. 겹친 940건은 `quality_issues`에 남기고 판매완료 상세값으로 쓰지 않습니다. 같은 기준일에 검증해 둔 기존 6개월 최저가·근거 링크, 3개월 평균가·표본 수, 검수 메모는 새 판매중 데이터와 함께 보존합니다. 근거가 없는 구성은 값을 만들지 않고 사이트에 `표본 미확보`로 표시합니다.

테이블별 역할과 안전 판정 방식은 [데이터 모델](docs/data-model.md)에 정리돼 있습니다.

## 중고나라 키워드 알림

로그인 세션은 Git이나 JSON에 저장하지 않고 macOS 키체인의
`com.55fries.joongna.session` 항목에서만 읽습니다. 현재 알림 확인과 키워드 검사는
데이터를 바꾸지 않습니다.

```bash
python3 scripts/manage_joongna_alerts.py list
python3 scripts/manage_joongna_alerts.py validate "Galaxy S23 Ultra"
```

등록·수정·삭제는 중고나라 계정의 실제 알림 설정을 바꿉니다. 가격은 원 단위입니다.
최저 가격은 기본 `100,000원`이며, 0원이나 하한 없는 알림은 만들지 않습니다.
최고 가격은 3개월 판매완료 평균보다 15% 낮은 금액을 1만 원 단위로 내림합니다.
기기 알림은 한글 검색어 하나만 등록해 영문 중복 알림을 만들지 않습니다.

```bash
python3 scripts/manage_joongna_alerts.py add "Galaxy S23 Ultra" --max-price 650000
python3 scripts/manage_joongna_alerts.py update 1234567 "Galaxy S23 Ultra" --max-price 600000
python3 scripts/manage_joongna_alerts.py remove 1234567
python3 scripts/manage_joongna_alerts.py sync-discounts
python3 scripts/manage_joongna_alerts.py sync-discounts --add-missing
```
