# Flight Friend FE 대개편 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 웹 화면을 shadcn/ui 기반으로 전면 재설계한다 — 메인 대시보드, 새 Trip(캘린더·검색·슬라이더), 결정 우선 Trip 상세, 제공자 배지 비교, /admin 정돈.

**Architecture:** 같은 앱(`flight_front/web`)을 제자리에서 교체한다. 먼저 도구(Vite 6, Tailwind v4, shadcn)와 공용 컴포넌트를 깔고, 백엔드 API에 필요한 키를 추가한 뒤, 화면을 하나씩 새 컴포넌트로 바꾼다. 옛 `apple-*` 토큰은 마지막에 제거한다.

**Tech Stack:** React 18, TypeScript, Vite 6, Tailwind v4, shadcn/ui(Radix), lucide-react, sonner, react-day-picker, cmdk, recharts / FastAPI, psycopg2, pytest.

**Spec:** `docs/superpowers/specs/2026-09-30-flight-friend-fe-redesign-design.md`

## Global Constraints

- API는 **키 추가만** — 기존 키 이름·의미를 바꾸지 않는다. 계산은 기존 domain 함수 재사용 (가격 기준·추적·알림 로직 불변).
- 테마: zinc + sky 강조(`--primary`), 제공자 색 Google Flights 파랑·Naver 초록(정의는 `providers.ts` 한 곳), Pretendard, 가격 `tabular-nums`, 카드 `rounded-2xl`, 다크 모드는 `.dark` 클래스.
- UI 컴포넌트는 `src/components/ui/`(shadcn), 공용은 `src/components/common/`, 경로 별칭 `@/` → `src/`.
- §8 슬롯(`DashboardTripCard`, `Sparkline`, `PriceHistoryChart`, `DateRangePicker`, `DestinationCombobox`, `BestComboHero`, `LegCard`, `SelectionPanel`, `EmptyState`)은 각각 한 파일·한 default export, Interfaces 블록의 props 고정.
- React 컴포넌트는 `fetch()` 직접 호출 금지 — `src/api.ts` 경유.
- 계층 규칙(`tests/test_architecture.py`): views/domain/providers/db/repo는 fastapi 금지, domain은 db/repo 금지, api/main은 providers 금지.
- 검증 명령: `DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights python -m pytest tests/ -q`, `python -m ruff check .`(0.16.9), `cd flight_front/web && npm run build`. 화면 검증은 `scripts/dev_seed.py` + `scripts/ui_snap.py`(Task 3)로 1200px·390px 스크린샷, 390px 가로 스크롤 없음.
- 각 task 끝에 `log.md` 항목 추가, 화면 task는 "브라우저로 본 것"과 "코드로만 본 것"을 구분해 기록.

## Review Focus

1. 방금 만든 Trip(스냅샷 0개)이 대시보드·상세에서 깨지지 않고 "첫 확인 중"으로 보인다 — Task 1 테스트(`best_combo`·`series`·`provider_totals`가 null/빈 값), Task 5·7 화면 확인.
2. 한 제공자만 데이터가 있을 때(Naver 차단 등) `provider_totals`가 키 1개이고 카드의 `GF보다 N원 쌈` 줄이 생략된다 — Task 1 테스트, Task 5 화면 확인.
3. "전체 다시 확인"이 보관된 Trip·진행 중·쿨다운 Trip을 건너뛰고 이유를 돌려준다 — Task 2 테스트.
4. 시간대 슬라이더 "제한 없음"(0–24)이 `null`로 저장되고 `"24:00"`이 API로 가지 않는다; 부분 범위 끝이 24면 `"23:59"`로 보낸다 — Task 6 스텝.
5. 긴 항공사명·긴 조건 라벨(`현대 M2/M3 Edition2(이용실적 충족시)`)이 390px에서 넘치지 않는다(말줄임 + 툴팁) — Task 7·8·9 스크린샷 확인.

---

### Task 1: 목록·상세 API 필드 추가

**Files:**
- Modify: `flight_friend/api/views.py` (`trip_list_item`, `_trip_dict`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `domain.results.cheapest_combo(in_condition(legs, prefs), prefs.max_price) -> (MergedLeg, MergedLeg, int) | None`, `current_legs`, `in_condition`, `domain.tracking.daily_series/run_values/tracking_stats/current_value`, `domain.schedule.refresh_interval(days)`, `repo.latest_run`, `repo.has_open_run`.
- Produces (`GET /api/trips` 각 항목에 추가; 기존 키 유지):
  - `best_combo`: `null` 또는 `{"out": LegSummary, "in": LegSummary, "total": int, "cond_total": int | null}`; `LegSummary = {"airline_iata", "airline_name", "dep_time", "arr_time", "stops", "flight_numbers", "best_provider"}`. `cond_total` = 두 편 각각 `min(best_cond.price, best_price)`의 합, 둘 다 `best_cond`가 없으면 null.
  - `provider_totals`: `{provider: int}` — 각 제공자마다, 그 제공자의 신선한 `ProviderPrice.price`만으로 가격을 매긴 편(그 제공자 가격이 없는 편은 제외)들 중 조건 안 최저 조합 합계. 조합을 만들 수 없는 제공자는 키 없음.
  - `series`: `[{"day": "YYYY-MM-DD", "combo": int | null, "partial": bool}]` (기존 `_day_point` 형식).
  - `low`, `low_day`, `is_low_now` (`current is not None and low is not None and current <= low`), `target_price`.
  - `next_auto_at`: ISO 문자열 또는 null — `trip.tracking and not archived and latest_run`이면 `latest_run.requested_at + refresh_interval(days_to_departure)`, 추적 중인데 run이 없으면 now, 아니면 null.
  - `provider_status`: `{provider: status}` — 제공자별 최신 run의 편도 스냅샷 두 개 중 나쁜 쪽(`error > blocked > empty > ok`).
  - `open_run_id`: queued/running run id 또는 null.
  - `GET /api/trips/{id}`의 `trip` 객체에도 `next_auto_at` (같은 규칙).

- [ ] **Step 1: 실패 테스트** (`tests/test_api.py`, 기존 시드 헬퍼 재사용)
  - `test_list_item_new_trip_nulls` — 스냅샷 없는 Trip: `best_combo is None`, `series == []`, `provider_totals == {}`, `provider_status == {}`, `is_low_now is False`, 추적 중이면 `next_auto_at`이 문자열.
  - `test_list_item_best_combo_and_provider_totals` — GF 가는 편 200,000·오는 편 150,000 / Naver 같은 항공편 180,000·160,000 → `best_combo.total == 330000`(가는 편 Naver 180,000 + 오는 편 GF 150,000), `best_combo.out.best_provider == "naver"`, `provider_totals == {"google_flights": 350000, "naver": 340000}`.
  - `test_list_item_single_provider_totals` — Naver 스냅샷만 → `provider_totals` 키가 `"naver"` 하나 (Review Focus 2).
  - `test_list_item_cond_total` — 가는 편에만 `best_cond` 161,700(`best_price` 171,000), 오는 편 조건부 없음(150,000) → `cond_total == 311700`.
  - `test_list_item_status_and_open_run` — Naver 가는 편 `blocked`·오는 편 `ok` → `provider_status["naver"] == "blocked"`; queued run 있으면 `open_run_id`가 그 id.
  - `test_trip_view_next_auto_at` — 추적 끔 → `trip.next_auto_at is None`.
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3:** 구현 — 헬퍼(`_leg_summary(m: MergedLeg) -> JsonDict`, `_provider_totals(legs, prefs) -> dict[str, int]`, `_next_auto_at(trip, now) -> str | None`, `_provider_status(snaps) -> dict[str, str]`)를 views.py에 둔다. `_provider_totals`는 제공자별로 `MergedLeg`를 그 제공자의 신선한 가격으로 다시 매겨 `in_condition` → `cheapest_combo`를 호출한다.
- [ ] **Step 4:** pytest 전체·ruff 통과.
- [ ] **Step 5: Commit** `feat(fe-api): dashboard fields on trip list, next_auto_at` (+ log.md)

---

### Task 2: 전체 다시 확인, 조회 단위 저장, admin 오류

**Files:**
- Modify: `flight_friend/api/main.py` (새 엔드포인트), `flight_friend/worker.py` (`_execute`), `flight_friend/repo.py` (`recent_runs` 스냅샷에 `error`), `flight_friend/api/views.py` (필요 시)
- Test: `tests/test_api.py`, `tests/test_worker.py`, `tests/test_repo_snapshots.py`

**Interfaces:**
- Produces:
  - `POST /api/trips/refresh` → 200 `{"queued": [int], "skipped": [{"trip_id": int, "reason": "running" | "cooldown"}]}`. 보관된 Trip(`views.is_archived`)은 결과에 넣지 않는다. 판정 순서: 열린 run → `running`, `cooldown_remaining > 0` → `cooldown`, 아니면 `repo.enqueue_run(id, "manual")`. 라우트는 `/api/trips/{trip_id}`보다 먼저 선언.
  - worker `_execute`: 각 조회 task가 끝나는 즉시 그 스냅샷을 `observed_at=datetime.now(UTC)`로 저장. 타임아웃 규칙(끝난 결과 유지, 멈춘 호출 `error "timeout"`, GF 타임아웃만 True 반환)은 불변.
  - `repo.recent_runs` 스냅샷 dict에 `"error": str | None`.
  - `GET /api/runs/{id}`는 이미 `snapshots`를 돌려준다 — 변경 없음.

- [ ] **Step 1: 실패 테스트**
  - `test_refresh_all_queues_and_skips` — Trip 4개: 정상 1, 열린 run 1, 방금 요청(쿨다운) 1, 보관(출국일 지남) 1 → `queued == [정상 id]`, `skipped`에 running·cooldown 각 1, 보관 Trip id는 어디에도 없음 (Review Focus 3).
  - `test_snapshot_saved_before_slow_provider_finishes` — 빠른 제공자와 `asyncio.Event`로 붙잡은 느린 제공자로 `execute_run` 실행 중, 빠른 제공자 스냅샷 3개가 DB에 먼저 보이고(`repo.load_snapshots`), Event를 풀면 6개.
  - `test_recent_runs_includes_snapshot_error` — error 스냅샷(`"http 403"`) → `recent_runs()[0]["snapshots"][i]["error"] == "http 403"`.
  - 기존 worker 타임아웃 테스트는 그대로 통과해야 한다.
- [ ] **Step 2:** FAIL 확인.
- [ ] **Step 3:** 구현 — `_execute`는 각 task에 `add_done_callback` 대신 `asyncio.as_completed`/task별 래퍼로 저장(동시 저장이 DB 연결을 공유하지 않게 각 저장은 자기 `repo.save_snapshot` 호출). 타임아웃 시 남은 task만 error로 저장.
- [ ] **Step 4:** pytest 전체·ruff 통과, `python -c "import flight_friend.worker"`.
- [ ] **Step 5: Commit** `feat(fe-api): refresh-all endpoint, per-call snapshot saves, admin snapshot errors` (+ log.md)

---

### Task 3: 도구 업그레이드·shadcn 초기화·검증 스크립트

**Files:**
- Modify: `flight_front/web/package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/index.css`, `src/main.tsx`
- Delete: `tailwind.config.*`, `postcss.config.*` (v4는 CSS-first — `apple-*` 토큰은 `index.css`의 `@theme`로 옮겨 옛 화면 유지)
- Create: `flight_front/web/components.json`, `src/lib/utils.ts`(`cn`), `src/components/ui/*`(§3.1 목록), `scripts/dev_seed.py`, `scripts/ui_snap.py`

**Interfaces:**
- Produces:
  - `@/` 별칭, `cn(...inputs)`.
  - shadcn 컴포넌트: Button, Card, Badge, Tabs, Sheet, Popover, Calendar, Command, Slider, Tooltip, Skeleton, Progress, Switch, Input, Label, Collapsible, Separator, Sonner(Toaster).
  - CSS 변수: shadcn 표준(`--background`, `--foreground`, `--card`, `--primary`(sky), `--muted`, `--border`, `--ring` …) + `--provider-google_flights`, `--provider-naver`, 라이트·다크 둘 다.
  - `scripts/dev_seed.py [--reset]`: 로컬 DB에 Trip 4개 시드 — (a) 추적 중·GF+Naver·14일치 run·조건부 있음·목표가, (b) Naver만(GF error), (c) 스냅샷 없음(방금 만듦), (d) 보관(출국일 지남). 실행 시 만든 trip id를 출력.
  - `scripts/ui_snap.py --base http://localhost:8000 --out <dir> [--dark] path...`: Playwright(Chromium `executable_path` 인자 `--chromium`, 기본 번들)로 각 경로를 1200px·390px 전체 스크린샷 + 390px에서 `document.documentElement.scrollWidth > innerWidth`면 경로를 출력하고 종료 코드 1.

- [ ] **Step 1:** Vite 6, `@vitejs/plugin-react` 최신, Tailwind v4 + `@tailwindcss/vite`로 올리고 `npm run build` 통과 확인(옛 화면은 `@theme`로 옮긴 `apple-*` 토큰으로 그대로 보인다).
- [ ] **Step 2:** shadcn 초기화(neutral=zinc, CSS 변수 on), 위 컴포넌트 추가, sky를 primary로, Pretendard CDN 링크(`index.html`), `body`에 `font-sans`·`tabular-nums`는 가격 요소에만.
- [ ] **Step 3:** `dev_seed.py`, `ui_snap.py` 작성.
- [ ] **Step 4:** 검증 — `npm run build`; API 기동 + 시드 + `ui_snap.py / /trips/<a> /trips/new /admin`로 옛 화면이 업그레이드 뒤에도 깨지지 않았는지 스크린샷 확인(라이트·다크). pytest·ruff(스크립트 포함) 통과.
- [ ] **Step 5: Commit** `chore(fe): vite 6, tailwind v4, shadcn/ui base, seed and snapshot scripts` (+ log.md)

---

### Task 4: 공용 컴포넌트와 앱 골격

**Files:**
- Create: `src/components/common/{ProviderBadge,ProviderPriceRow,CondPriceTag,StaleBadge,Money,Sparkline,EmptyState,ErrorState}.tsx`, `src/components/layout/AppShell.tsx`
- Modify: `src/components/trip/providers.ts` → `src/lib/providers.ts`로 이동(import 갱신), `src/App.tsx`, `src/components/ThemeToggle.tsx`(shadcn Button)

**Interfaces:**
- Produces:
  - `providers.ts`: `PROVIDERS: Record<string, {label: string; initial: string; colorVar: string}>` (`google_flights` → `"Google Flights"`, `"G"`; `naver` → `"Naver"`, `"N"`), `providerLabel(id)`, `providerMeta(id)` (모르는 id → 회색, 이름 첫 글자 대문자).
  - `ProviderBadge({ provider: string; size?: "sm" | "md" })`
  - `ProviderPriceRow({ prices: ProviderPriceView[]; bestProvider: string | null })` — `[N] 171,000 ✓ · [G] 171,700`, stale은 흐리게 + `StaleBadge`.
  - `CondPriceTag({ price: number; label: string | null })` — lucide `CreditCard` 아이콘 + `Money`, 툴팁 `"{label} 적용 시"`; 라벨 말줄임.
  - `StaleBadge({ observedAt: string; windowMinutes?: number })` — 툴팁 `"{timeAgo} 확인 · 신선도 기준 {N시간}"`.
  - `Money({ value: number; className?: string })` → `171,000원`.
  - `Sparkline({ points: {day: string; combo: number | null}[]; low?: number | null })` — 슬롯.
  - `EmptyState({ icon: LucideIcon; title: string; description?: string; action?: ReactNode })` — 슬롯. `ErrorState({ message: string; onRetry?: () => void })`.
  - `AppShell({ actions?: ReactNode; children })` — 상단 바(제목→`/`, `/admin` 링크, ThemeToggle, `actions`), 본문 `max-w-[1200px] px-4`, 전역 `<Toaster />`.

- [ ] **Step 1:** 컴포넌트 구현. 기존 화면의 제공자 표시 import를 새 `providers.ts`로 바꾼다(동작 동일).
- [ ] **Step 2:** `App.tsx`를 `AppShell`로 감싼다(페이지 내용은 아직 옛 컴포넌트).
- [ ] **Step 3:** 검증 — build; 시드 + `ui_snap.py`로 네 경로 1200/390 확인(상단 바, 다크 토글).
- [ ] **Step 4: Commit** `feat(fe): shared provider/price components and app shell` (+ log.md)

---

### Task 5: 메인 대시보드

**Files:**
- Create: `src/pages/Dashboard.tsx`, `src/components/dashboard/DashboardTripCard.tsx`
- Modify: `src/types.ts` (`TripSummary` 필드 추가 — Task 1 키 그대로), `src/api.ts` (`refreshAll(): Promise<{queued: number[]; skipped: {trip_id: number; reason: "running" | "cooldown"}[]}>`), `src/App.tsx` (`/` → Dashboard)
- Delete: `src/pages/TripList.tsx`
- Create: `src/data/airports.ts` (Task 6도 사용 — `AIRPORTS: {code, city, name, country}[]`, `cityName(code): string | null`; 일본 주요 공항 전체 + ICN·GMP·TPE·HKG·BKK·DAD·SGN·MNL·CEB·SIN·PVG·KIX 등 근거리)

**Interfaces:**
- Consumes: Task 1 목록 필드, Task 2 `POST /api/trips/refresh`, Task 4 공용 컴포넌트.
- Produces: `DashboardTripCard({ trip: TripSummary })` (슬롯), `Dashboard` 페이지.

- [ ] **Step 1:** 타입·API 갱신 → build.
- [ ] **Step 2:** `DashboardTripCard` — spec §4.2의 1–7 순서·문구 그대로:
  - 머리 `{cityName ?? code} {code}`, `MM.DD(요일) – MM.DD(요일) · N박 N+1일`, `D-N`.
  - 가격 `Money`(크게) + `ProviderBadge` — 두 편의 `best_provider`가 같으면 배지 하나, 다르면 두 개(가는 편 먼저) + `provider_totals`에 다른 제공자가 있으면 `"{다른 제공자 라벨}보다 {차이}원 쌈"`(내 쪽이 더 쌀 때만) + `cond_total`이 있으면 `CondPriceTag`.
  - `Sparkline`(series 3일 미만이면 `데이터 쌓는 중`), 통계 줄 `시작 대비 ▼3%`/`▲`, `최저 312,000 (10/02)`, `is_low_now`면 `지금이 최저` 배지.
  - 조합 요약 두 줄, 목표가 있으면 Progress + `목표까지 N원`/`목표 달성`.
  - 바닥줄 `timeAgo(current_observed_at) 확인 · 다음 자동 HH:MM` + 제공자 상태 점; `open_run_id`면 스피너 `확인 중…`; `best_combo`가 null이고 run이 있으면 `첫 확인 중…`, 없으면 `아직 확인 전` (Review Focus 1).
- [ ] **Step 3:** `Dashboard` — 상단 `내 여행` + `새 Trip`·`전체 다시 확인`(AppShell actions), 그리드 1열/`lg:` 2열, 보관 Trip은 Collapsible `지난 여행 (N)`, 빈 상태 `EmptyState(title="첫 여행을 저장해 보세요")`, 로딩 Skeleton 카드 2개, 오류 `ErrorState`. `open_run_id`가 하나라도 있으면 3초 폴링, 없으면 중지. 전체 확인 토스트 `"{q}개 확인 요청 · {c}개 쿨다운 · {r}개 진행 중"`(0인 항목 생략).
- [ ] **Step 4:** 검증 — build; 시드 4종 + `ui_snap.py /` 라이트·다크, 1200/390, 가로 스크롤 없음. 시드 (b)에서 `GF보다` 줄 없음, (c) `첫 확인 중` 또는 `아직 확인 전` 확인.
- [ ] **Step 5: Commit** `feat(fe): dashboard home with trip cards and refresh-all` (+ log.md)

---

### Task 6: 새 Trip과 공용 조건 입력

**Files:**
- Create: `src/components/inputs/{DateRangePicker,DestinationCombobox,TimeWindowSlider,AirlineChips}.tsx`, `src/components/trip/ConditionFields.tsx`
- Modify: `src/pages/NewTrip.tsx` (재작성), `src/utils.ts` (시간 변환)

**Interfaces:**
- Consumes: `src/data/airports.ts`, `createTrip(input)` (기존).
- Produces:
  - `DateRangePicker({ value: {from?: Date; to?: Date}; onChange(v): void })` — 슬롯. react-day-picker range, ko locale, `numberOfMonths` 데스크톱 2·모바일 1, 오늘 이전과 `to <= from` 비활성, 아래 요약 `MM.DD(요일) – MM.DD(요일) · N박 N+1일`.
  - `DestinationCombobox({ value: string; onChange(code: string): void })` — 슬롯. cmdk로 도시·공항명·코드 검색, 표에 없는 3글자 영문 입력은 `"XXX 직접 입력"` 항목으로 허용(대문자).
  - `TimeWindowSlider({ label: string; value: [string, string] | null; onChange(v: [string, string] | null): void })` — 0–1440분, step 30. UI 값 `[0, 1440]` ↔ `null`; 그 외는 `"HH:MM"` 쌍, 끝이 1440이면 `"23:59"` (Review Focus 4). 표시 `06:00 – 12:00` / `제한 없음`.
  - `ConditionFields({ prefs: Preferences; onChange(p: Preferences): void })` — 시간대 슬라이더 2개, 직항 Switch, Collapsible "상세 조건"(포함·제외 `AirlineChips`, 최대 가격, 최대 비행시간). Task 8의 조건 시트가 재사용.
  - `utils.ts`: `minutesToHHMM(m: number): string`, `hhmmToMinutes(s: string): number`, `windowToSlider(v): [number, number]`, `sliderToWindow([a, b]): [string, string] | null`.

- [ ] **Step 1:** 입력 컴포넌트·`ConditionFields` 구현.
- [ ] **Step 2:** `NewTrip` 재작성 — spec §5 순서, 가운데 카드 `max-w-[640px]`, 추적 Switch 기본 on, 목표가 Input, 만들기 → `createTrip` → `/trips/{id}` 이동 + 토스트 `Trip을 만들었어요 · 확인 중`. 서버 422는 필드 옆 문구로.
- [ ] **Step 3:** 검증 — build; `ui_snap.py /trips/new` 1200/390; Playwright로 FUK 검색 선택 → 날짜 두 번 클릭 → 가는 편 슬라이더를 06–12로 → 만들기까지 진행해 생성된 Trip의 `prefs.out_dep_window == ["06:00","12:00"]`, `in_dep_window is None`을 API로 확인하고 지운다.
- [ ] **Step 4: Commit** `feat(fe): new trip with range calendar, destination search, time sliders` (+ log.md)

---

### Task 7: Trip 상세 — 머리·"지금 최선"·진행 표시

**Files:**
- Create: `src/components/trip/{TripHeader,RunProgress,BestComboHero,CandidateChips,NearMissLine,TripSettingsSheet}.tsx`
- Modify: `src/pages/TripPage.tsx` (새 골격: 머리 → Hero → 후보 → (Task 8 영역은 기존 LegList/SelectionBar 유지) ), `src/types.ts` (`TripInfo.next_auto_at`)
- Delete: `src/components/trip/{StatusHeader,TrackingSummary,Candidates,NearMissHint,TripSettings}.tsx` (대체된 것만)

**Interfaces:**
- Consumes: `TripView`(기존 + `trip.next_auto_at`), `getRun(id)`의 `snapshots`, `startRun`, `patchTrip`.
- Produces:
  - `TripHeader({ view: TripView; onRun(): void; running: boolean; cooldownSeconds: number | null; onOpenSettings(): void })` — spec §6.1 문구; 상태 줄 `timeAgo 확인 · 다음 자동 HH:MM · [G]✓ [N]✕`.
  - `RunProgress({ snapshots: {provider; kind; direction; status}[]; providers: string[] })` — 조회 6칸 칩 `G 가는편 ✓ · G 오는편 … · G 왕복 … · N …`, 저장된 것은 ✓/✕, 나머지 `…`.
  - `BestComboHero({ view: TripView; onSelect(outKey: string, inKey: string): void; onJump(direction: "out" | "in", key: string): void })` — 슬롯. 조건 안 최저 조합 = `view.candidates` 중 `price` 최소(동가면 첫 번째); 없으면 `EmptyState("조건에 맞는 조합이 없어요")`. 편마다 시각·항공사·직항·`ProviderBadge`·예약 버튼(최저가 제공자 `booking_url`, Naver면 `판매사 선택`). 카드 조건 합계(`CondPriceTag`). 추적 요약(`시작 대비`, `최저`, `Sparkline` — `getHistory`) 데스크톱 오른쪽/모바일 아래.
  - `CandidateChips({ candidates: CandidateView[]; legs: TripView["legs"]; onSelect(outKey, inKey) })`, `NearMissLine({ nearMiss: NearMissView | null; onJump(direction, key) })` 문구 `"{violated 설명}을 풀면 {saving}원 쌈 →"`.
  - `TripSettingsSheet({ view; onSaved(view) })` — 추적 Switch, 목표가(비우면 해제), 저장 토스트 `저장했어요`.

- [ ] **Step 1:** 컴포넌트 구현, `TripPage`에 머리·진행·Hero·후보·near-miss 배치. 확인 중이면 `getRun` 2초 폴링으로 `RunProgress` 갱신, 끝나면 `getTrip` 재조회.
- [ ] **Step 2:** 검증 — build; 시드 (a)(b)(c)로 `ui_snap.py /trips/<id>` 1200/390 라이트·다크; "지금 확인" 클릭 뒤 진행 칩이 채워지는 것 확인(로컬 worker 없이 확인하려면 dev_seed에 `--fake-run` 옵션으로 스냅샷을 몇 초 간격으로 넣는 방식 추가 가능 — Task 3 스크립트 확장 허용).
- [ ] **Step 3: Commit** `feat(fe): trip header, run progress, best-combo hero` (+ log.md)

---

### Task 8: Trip 상세 — 항공편 목록·선택 패널·가격 추이

**Files:**
- Create: `src/components/trip/{LegTabs,ConditionSheet,SelectionPanel,PriceHistoryChart}.tsx`
- Modify/재작성: `src/components/trip/LegCard.tsx`, `src/pages/TripPage.tsx`
- Delete: `src/components/trip/{LegList,FilterBar,SelectionBar,HistoryChart,Results}.tsx`

**Interfaces:**
- Consumes: Task 6 `ConditionFields`, Task 7 `onJump/onSelect` 계약, `patchTrip`.
- Produces:
  - `LegCard({ leg: MergedLegView; direction: "out" | "in"; selected: boolean; highlighted: boolean; onSelect(): void })` — 슬롯. 왼쪽 시각(+1)·항공사(말줄임)·직항/경유(경유는 amber)·소요, 오른쪽 `ProviderPriceRow` + `CondPriceTag`(best_cond) + stale 처리. 펼침(기본 접힘, 버튼 텍스트 `상세 ▾/▴`가 라벨) — 편명, 제공자별 링크(`예약 ↗`/`판매사 선택 ↗`), 조건부 줄 `└ {cond_label} {Money}` + 링크. `id=legDomId(direction, key)` 유지.
  - `LegTabs({ view; selected: {out?: string; in?: string}; highlighted: string | null; onSelect(direction, key) })` — Tabs `가는 편 (N)`/`오는 편 (N)`, 조건 안 목록 + Collapsible `조건 밖 N개`.
  - `ConditionSheet({ view; onSaved(view) })` — 요약 칩(`출발 06–12시 · 직항`, 조건 없으면 `조건 없음`) → Sheet에 `ConditionFields` → `patchTrip({prefs})`, 응답 `trip.id`가 현재 id와 다르면 무시(기존 가드 유지).
  - `SelectionPanel({ out: MergedLegView | null; inn: MergedLegView | null; outDate: string; retDate: string; rtReference: RtReference[] })` — 슬롯. `lg:` 이상 오른쪽 sticky, 미만은 하단 한 줄 바 `합계 {Money} · N박 ›` → Sheet. 내용: 두 편, 합계, 카드 조건 합계(더 쌀 때만), 현지 체류, 왕복 참고 한 줄 `같은 항공사 왕복 {Money} · {provider}`, 편별 예약 버튼.
  - `PriceHistoryChart({ points: DayPoint[]; target?: number | null })` — 슬롯. Collapsible `가격 추이` 안, 최저점 마커·목표가 기준선·부분 데이터 날 표시.

- [ ] **Step 1:** 구현하고 `TripPage`를 데스크톱 2단(`lg:grid-cols-[1fr_360px]`) / 모바일 1단 + 하단 바로 완성. Hero의 `onJump`는 해당 탭으로 전환 후 스크롤·강조.
- [ ] **Step 2:** 검증 — build; 시드 (a)(b)로 1200/390 라이트·다크, 390px 하단 바 한 줄·가로 스크롤 없음, 긴 조건 라벨 말줄임 (Review Focus 5), 조건 시트 저장 후 목록 갱신.
- [ ] **Step 3: Commit** `feat(fe): leg tabs, selection panel, condition sheet, price history` (+ log.md)

---

### Task 9: /admin·마무리·정리

**Files:**
- Modify/재작성: `src/pages/Admin.tsx`, `src/types.ts` (`AdminRun.snapshots[].error`), `src/index.css` (`apple-*` 토큰 제거), `src/utils.ts` (안 쓰는 함수 제거)
- Delete: 참조가 사라진 옛 컴포넌트 전부
- Modify: `AGENTS.md` (§2 Web 행: shadcn/ui·`@/`·`components/{ui,common,layout,dashboard,inputs,trip}`, §3 파일 위치 표, §12 명령어에 `scripts/dev_seed.py`·`scripts/ui_snap.py`), `TODOS.md` (FE 대개편 항목 완료 처리, 21st.dev 슬롯 교체 항목 추가), `log.md`

**Interfaces:**
- Consumes: Task 2 `snapshots[].error`.

- [ ] **Step 1:** Admin — 최근 실행: `ProviderBadge` + 상태 칩(`✓` / `차단 의심` / `결과 없음` / `오류`), 실패 칩 툴팁에 `error`; 제공자별 일자 성공률 표 + 작은 막대; `<640px`는 카드 목록. 로딩 Skeleton·오류 `ErrorState`.
- [ ] **Step 2:** `rg "apple-"`가 `src/`에서 0건이 되도록 옛 토큰·클래스 제거, 안 쓰는 컴포넌트·함수 삭제, `npm run build` 경고 없음.
- [ ] **Step 3:** 전 화면 점검 — 시드 4종으로 `/`, `/trips/new`, `/trips/<a>`, `/trips/<b>`, `/trips/<c>`, `/admin`을 1200/390 라이트·다크 스크린샷, 가로 스크롤 0건 (Review Focus 5 포함).
- [ ] **Step 4:** pytest·ruff·build 통과, 문서 갱신.
- [ ] **Step 5: Commit** `feat(fe): admin redesign, remove legacy tokens and components` (+ log.md)
