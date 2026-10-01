# Flight Friend FE 대개편 설계

- 작성일: 2026-09-30
- 상위 설계: `2026-09-28-flight-friend-v2-design.md` (제품·IA), `2026-09-30-flight-friend-m2-naver-design.md` (제공자·조건부 가격)
- 상태: 합의 완료, 구현 계획 대기

## 1. 목표와 성공 기준

M1·M2에서 "일단 동작하게" 만든 웹 화면(`flight_front/web`)을 전면 재설계한다. 중요도는 **시각 완성도 > 정보 구조 > 모바일** 순.

성공 기준:

1. 모든 화면이 shadcn/ui 기반의 한 가지 디자인 체계(토큰·글꼴·카드·배지)로 통일되고 다크 모드가 유지된다.
2. 어느 화면에서든 가격이 **어느 제공자의 것인지** 배지로 바로 보이고, 제공자 간 가격 차이가 펼치지 않고 보인다.
3. 메인은 저장한 Trip들의 **대시보드**다. 카드 한 장으로 "지금 살지/기다릴지" 판단할 정보가 보이고, 한 번에 전체 다시 확인할 수 있다.
4. Trip 상세 첫 화면에 "지금 최선" 조합과 예약 버튼이 있다.
5. 새 Trip은 범위 캘린더·목적지 검색·시간대 슬라이더로 만든다.
6. 390px 폭에서 가로 스크롤이 없고, 선택 바가 한 줄로 요약된다.

범위 밖: 계산 로직 변경(가격 기준·추적·알림은 M2 그대로), Skyscanner 제공자(다음 작업), 프론트 단위 테스트 도입.

## 2. 결정 사항

| # | 결정 |
|---|---|
| F-D1 | 범위: 전면 재설계 (시각 > 정보 구조 > 모바일) |
| F-D2 | 컴포넌트 출처: shadcn/ui 기반. 21st.dev·Mobbin은 "컴포넌트 슬롯" 단위로 사용자가 골라 교체 (§8) |
| F-D3 | 제공자 구분: 제공자 배지(이니셜·고유색) + 카드 안 제공자별 가격 나란히 |
| F-D4 | Trip 상세: 결정 우선("지금 최선" 카드) + 데스크톱 2단(오른쪽 선택 패널) / 모바일 하단 바 |
| F-D5 | 자잘한 변경 11개 모두 포함 (§7) |
| F-D6 | 메인: 대시보드 카드 (§4) + 전체 다시 확인 |
| F-D7 | 구현: 제자리 교체 + 도구 먼저 업그레이드 (Vite 6, Tailwind v4) |
| F-D8 | 테마: 모던 뉴트럴 (zinc + sky 강조, Pretendard, `rounded-2xl`) |

## 3. 기반 (F0)

### 3.1 도구

- Vite 4 → 6, Tailwind v3 → v4 (`@tailwindcss/vite`, CSS-first 설정). React 18·react-router·recharts 유지.
- shadcn/ui 초기화: `components.json`, 경로 별칭 `@/` → `src/`, UI 컴포넌트는 `src/components/ui/`.
- 추가 의존성: Radix(shadcn이 요구하는 것), `class-variance-authority`, `tailwind-merge`, `clsx`, `lucide-react`, `sonner`, `react-day-picker`(ko locale, date-fns), `cmdk`.
- 기본 컴포넌트: Button, Card, Badge, Tabs, Sheet, Popover, Calendar, Command, Slider, Tooltip, Skeleton, Progress, Switch, Input, Label, Collapsible, Separator.

### 3.2 디자인 토큰

- 색: shadcn zinc 팔레트 + 강조색 sky (`--primary`). 상태색: 하락/성공 green, 상승/경고 amber, 오류 red.
- 제공자 색: Google Flights 파랑, Naver 초록. `providers.ts` 한 곳에서 정의 (이니셜·표시명·색).
- 다크 모드: 기존 ThemeToggle 유지, `.dark` 클래스 방식.
- 글꼴: Pretendard(CDN, `index.html`의 stylesheet 링크). 가격 숫자는 `tabular-nums`.
- 모서리: 카드 `rounded-2xl`, 컨트롤 `rounded-lg`.
- 기존 `apple-*` 토큰은 F5에서 제거 (그전까지 옛 화면이 깨지지 않게 병존).

### 3.3 공용 컴포넌트 (`src/components/common/`)

| 컴포넌트 | 역할 |
|---|---|
| `ProviderBadge` | 제공자 이니셜 배지 (색·툴팁=표시명). 모르는 제공자는 회색 + 이름 앞글자 |
| `ProviderPriceRow` | 제공자별 가격 나란히: `[N] 171,000 ✓최저 · [G] 171,700`. 오래된 가격은 흐리게 + `StaleBadge` |
| `CondPriceTag` | 카드 아이콘 + 조건부 가격, 툴팁에 조건 이름 |
| `StaleBadge` | "오래됨" 배지, 툴팁 `3시간 전 확인 · 신선도 기준 2시간` |
| `Money` | 원화 표기(`171,000원`), `tabular-nums` |
| `Sparkline` | 일별 최저가 미니 라인(recharts), 최저점 마커 |
| `EmptyState`, `ErrorState` | 아이콘·한 줄 설명·행동 버튼 |

### 3.4 앱 골격

- 상단 바: 로고/제목(홈 링크), `/admin` 링크, 테마 토글. 메인에서는 오른쪽에 "새 Trip"·"전체 다시 확인".
- 본문 최대 폭 1200px, 좌우 16px 여백(모바일).
- `sonner` Toaster 전역 1개.

## 4. 메인 대시보드 (`/`, F2)

### 4.1 화면

- 카드 그리드: 모바일 1열, 데스크톱(≥1024px) 2열. 추적 중·출발 임박 순 정렬 (기존 목록 순서 규칙 유지).
- 보관된 Trip은 맨 아래 접힌 "지난 여행" 영역.
- Trip이 없으면 `EmptyState`("첫 여행을 저장해 보세요" + 새 Trip 버튼).
- 확인 중인 Trip이 하나라도 있으면 목록을 3초마다 다시 불러오고, 모두 끝나면 멈춘다.

### 4.2 Trip 카드 (슬롯 `DashboardTripCard`)

위에서 아래로:

1. 머리: 도시명 + 코드(`후쿠오카 FUK`), `11.12(목) – 11.16(월) · 4박 5일`, `D-42`, 추적 중 표시.
2. 가격: 현재 최저 조합가(크게) + 최저가 제공자 배지 + `GF보다 12,000원 쌈`(다른 제공자 최저 조합가와의 차이, 다른 제공자 값이 없으면 생략) + `CondPriceTag`(카드 조건 합계, 있을 때).
3. 추이: `Sparkline` (일별 최저가). 데이터 3일 미만이면 "데이터 쌓는 중".
4. 통계 줄: `시작 대비 ▼3%` · `최저 312,000 (10/02)` · "지금이 최저" 배지(`is_low_now`일 때).
5. 최저 조합 요약: 가는 편·오는 편 각 한 줄 — 항공사, 출발→도착 시각, 직항/경유 N.
6. 목표가 진행도: 목표가가 있을 때만 — 막대 + `목표까지 18,000원` 또는 `목표 달성`.
7. 바닥줄: `3분 전 확인 · 다음 자동 16:25` + 제공자 상태 점(최신 편도 스냅샷 기준 ✓/✕) / 확인 중이면 스피너 `확인 중…`.

카드 전체가 Trip 상세 링크.

### 4.3 전체 다시 확인

- 버튼 → `POST /api/trips/refresh` → 토스트 `3개 확인 요청 · 1개 쿨다운 · 1개 진행 중`.
- 요청 직후 목록을 다시 불러와 해당 카드가 "확인 중"으로 바뀐다.

## 5. 새 Trip (`/trips/new`, F3)

- 가운데 카드(최대 640px), 모바일 전체 폭.
1. 목적지 — 슬롯 `DestinationCombobox`: cmdk 콤보박스, 도시명·공항명·코드 검색. 공항 표는 프론트 `src/data/airports.ts` (코드·도시명·공항명·국가; 일본 주요 공항 전체 + 근거리 주요 공항). 표에 없어도 3글자 영문 코드는 직접 입력 허용(대문자 정규화).
2. 날짜 — 슬롯 `DateRangePicker`: react-day-picker range 모드, 데스크톱 2개월/모바일 1개월, 오늘 이전 비활성, 선택 요약 `11.12(목) – 11.16(월) · 4박 5일`. 귀국일은 출발일 다음 날 이후만.
3. 출발 시간대 — `TimeWindowSlider` ×2(가는 편·오는 편): 0:00–24:00, 30분 단위, 기본 "제한 없음"(0–24 = null로 저장). 시작 > 끝 입력이 구조적으로 불가.
4. 조건: 직항만 스위치. "상세 조건" Collapsible — 포함·제외 항공사 칩, 최대 가격, 최대 비행시간 (기존 prefs 필드 그대로).
5. 추적: 스위치(기본 켜짐), 목표가(선택).
6. 만들기 → 기존 `POST /api/trips`(첫 run 자동 enqueue) → Trip 상세로 이동 + 토스트 `Trip을 만들었어요 · 확인 중`.

Trip 상세의 조건 편집(시트)도 같은 `TimeWindowSlider`·스위치·칩을 쓴다.

## 6. Trip 상세 (`/trips/:id`, F4)

### 6.1 머리

- 뒤로가기, `후쿠오카 FUK · 11.12–11.16 · 4박 5일 · D-42`.
- 상태 줄: `3분 전 확인 · 다음 자동 16:25 · G ✓ N ✓`.
- "지금 확인" 버튼(쿨다운이면 남은 시간 표시) + ⚙ 설정 시트(추적 스위치, 목표가 — 기존 TripSettings 기능).
- 확인 중 진행: 버튼 아래 조회 단위 칩 `G 가는편 ✓ · G 오는편 … · G 왕복 … · N 가는편 ✓ · …` — 저장된 스냅샷부터 ✓/✕.

### 6.2 "지금 최선" 카드 (슬롯 `BestComboHero`)

- 조건 안 최저 조합(기존 cheapest combo) 합계 크게 + 카드 조건 합계 태그.
- 가는 편·오는 편 두 줄: 시각·항공사·직항 여부·최저가 제공자 배지·예약 버튼(최저가 제공자 링크; Naver는 "판매사 선택").
- 추적 요약(시작 대비·최저가·미니 그래프): 데스크톱은 카드 오른쪽, 모바일은 아래.
- 조건 밖 제안(near-miss)이 있으면 카드 아래 한 줄 `출발 시간을 06시까지 늘리면 21,000원 쌈 →` (누르면 해당 항공편으로 스크롤·강조).
- 대표 후보(파레토) 2–3개 가로 칩 — 누르면 두 편 선택.
- 조합이 없으면 `EmptyState`("조건에 맞는 조합이 없어요" + 조건 시트 열기).

### 6.3 항공편 목록

- Tabs `가는 편 (32)` / `오는 편 (28)`. 탭 위 필터 요약 칩(`출발 06–12시 · 직항`) → 조건 시트.
- LegCard(슬롯 `LegCard`): 왼쪽 출발→도착 시각(+1 표시)·항공사·직항/경유·소요 시간 / 오른쪽 `ProviderPriceRow` + `CondPriceTag` + `StaleBadge`. 펼치면 편명·제공자별 링크(조건부 링크 포함). 선택·강조 상태 유지.
- 조건 밖 항공편은 목록 끝 Collapsible "조건 밖 N개".

### 6.4 선택한 조합 (슬롯 `SelectionPanel`)

- 데스크톱: 오른쪽 sticky 패널 — 선택한 두 편, 합계, 카드 조건 합계, 현지 체류, 왕복 참고 한 줄(`같은 항공사 왕복 345,000 · Naver`), 편별 예약 버튼.
- 모바일: 하단 한 줄 바 `합계 318,000 · 4박 ›` → 누르면 같은 내용의 Sheet.

### 6.5 가격 추이

- Collapsible "가격 추이" — 기존 HistoryChart를 새 스타일로: 일별 최저 라인, 최저점 마커, 목표가 기준선, 부분 데이터 날 표시.

## 7. 자잘한 변경 (모두 포함)

1. 날짜 범위 캘린더 (§5)
2. 목적지 검색 콤보박스 (§5)
3. 시간대 슬라이더 (§5, 조건 시트 공용)
4. Trip 카드 요약 강화 (§4.2)
5. 제공자별 진행 표시 (§6.1)
6. 다음 자동 확인 시각 (§4.2, §6.1)
7. 오래된 가격 배지·툴팁 (`StaleBadge`)
8. 로딩 스켈레톤·빈 상태·오류 상태 (모든 페이지)
9. 토스트 (설정 저장, 확인 요청, 전체 확인 결과, 오류)
10. 리뷰 잔여: 토글 라벨 접근성(보이는 글자가 라벨), 390px 선택 바(§6.4), 왕복 참고 문장 단축(§6.4)
11. /admin 가독성 (§9)

## 8. 21st.dev·Mobbin 슬롯

구현은 shadcn 기본 컴포넌트로 끝까지 한다. 아래 슬롯은 각각 **한 파일·한 컴포넌트**로 만들고 props를 고정해, 사용자가 21st.dev 링크나 Mobbin 화면을 주면 그 슬롯만 교체한다.

| 슬롯 | 위치 |
|---|---|
| `DashboardTripCard` | 메인 카드 |
| `Sparkline` / `PriceHistoryChart` | 카드 미니 그래프 / 상세 가격 추이 |
| `DateRangePicker` | 새 Trip 날짜 |
| `DestinationCombobox` | 새 Trip 목적지 |
| `BestComboHero` | 상세 "지금 최선" |
| `LegCard` | 상세 항공편 행 |
| `SelectionPanel` | 상세 선택 패널/하단 바 |
| `EmptyState` | 공통 빈 상태 |

## 9. /admin (F5)

- 최근 실행 표: 제공자 배지, 스냅샷 상태 칩(`✓ / 차단 의심 / 결과 없음 / 오류`), 실패 스냅샷 오류 메시지 툴팁(`http 403`, `timeout`, `partners 18/20`).
- 제공자별 일자 성공률: 표 + 작은 막대.
- 모바일(<640px)에서는 표 대신 카드 목록.

## 10. 백엔드 변경 (F1)

API는 **키 추가만** (기존 키 이름·의미 불변). 계산은 기존 domain 함수를 재사용한다.

### 10.1 `GET /api/trips` 항목 추가 필드

| 필드 | 내용 |
|---|---|
| `best_combo` | `{out: LegSummary, in: LegSummary, total, cond_total}` 또는 null. LegSummary = `{airline_iata, airline_name, dep_time, arr_time, stops, flight_numbers, best_provider}`. 조건 안 최저 조합(`cheapest_combo`) 기준 |
| `provider_totals` | `{provider: 그 제공자의 신선한 가격만으로 만든 조건 안 최저 조합가}` (값을 낼 수 없는 제공자는 제외) |
| `series` | `[{day, combo, partial}]` — `daily_series(run_values(...))` 그대로 |
| `low`, `low_day`, `is_low_now` | 추적 통계. `is_low_now` = `current`가 있고 `current <= low` |
| `target_price` | Trip 목표가 |
| `next_auto_at` | 추적 중·보관 아님이면 `마지막 run 요청 시각 + refresh_interval(D-day)`, 아니면 null |
| `provider_status` | `{provider: 최신 편도 스냅샷 status}` (출국·귀국 중 나쁜 쪽: error > blocked > empty > ok) |
| `open_run_id` | queued/running run이 있으면 그 id, 없으면 null |

마지막 확인 시각은 기존 `current_observed_at`을 그대로 쓴다.

### 10.2 `POST /api/trips/refresh`

- 보관되지 않은 모든 Trip에 대해: 열린 run이 있으면 `skipped: running`, 수동 쿨다운 중이면 `skipped: cooldown`, 아니면 manual run enqueue.
- 응답 200: `{"queued": [trip_id...], "skipped": [{"trip_id", "reason"}]}`.

### 10.3 조회 단위 저장과 실행 진행

- worker `_execute`: 각 조회 task가 끝나는 즉시 그 스냅샷을 저장한다(현재는 전부 끝난 뒤 일괄 저장). 타임아웃 처리(끝난 결과 유지, 멈춘 호출은 `timeout` error)는 그대로.
- `GET /api/runs/{id}` 응답에 `snapshots: [{provider, kind, direction, status}]` 추가 (그 run에 지금까지 저장된 것).

### 10.4 기타

- `GET /api/trips/{id}` trip 정보에 `next_auto_at` 추가 (10.1과 같은 규칙).
- `GET /api/admin/runs`의 스냅샷 요약에 `error` 추가.

## 11. 단계와 검증

한 브랜치·한 PR. 각 단계 끝에서 앱이 동작한다.

| 단계 | 내용 |
|---|---|
| F0 | 도구 업그레이드, shadcn 초기화, 토큰·글꼴, 공용 컴포넌트, 앱 골격·토스트 |
| F1 | 백엔드 §10 (pytest) |
| F2 | 메인 대시보드 + 전체 다시 확인 |
| F3 | 새 Trip + 공용 조건 시트 |
| F4 | Trip 상세 |
| F5 | /admin, 공통 상태 마무리, `apple-*` 토큰·옛 컴포넌트 삭제, 전 화면 점검 |

검증:
- 백엔드: `pytest tests/`, `ruff check .` (0.16.9).
- 프론트: 매 단계 `npm run build`; 헤드리스 Chromium으로 시드 데이터 화면을 1200px·390px 스크린샷 확인(다크 모드 1회 포함), 390px 가로 스크롤 없음.
- 프론트 단위 테스트는 도입하지 않는다 (계산은 백엔드 pytest).

## 12. 리스크

| 리스크 | 대응 |
|---|---|
| Tailwind v4·Vite 6 업그레이드로 기존 화면 스타일 깨짐 | F0에서 빌드·스크린샷 확인. 옛 토큰은 F5까지 병존 |
| 목록 API가 Trip마다 스냅샷 전체를 읽어 느려짐 | 개인 도구 규모(수십 개)에선 허용. 느려지면 캐시 |
| 21st.dev 컴포넌트가 추가 라이브러리(framer-motion 등)를 요구 | 슬롯 교체 시점에 판단, 기본 구현은 의존성 최소 |
| 전체 다시 확인이 worker 큐를 길게 만듦 (Trip당 ~30초) | 카드별 "확인 중" 표시, 쿨다운·중복 요청 건너뜀 |
