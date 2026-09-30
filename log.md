# 작업 로그 (Work Log)

> Claude Code와 Codex가 task 단위로 번갈아 작업한다. **작업을 시작하기 전에 이 파일의 최신 항목과
> "현재 상태"를 먼저 읽고, 작업이 끝나면 항목을 추가한다.** 최신 항목이 맨 아래.
>
> 항목 형식:
> ```
> ## YYYY-MM-DD — <작업자: Claude Code | Codex> — <task 제목>
> - 브랜치 / 커밋:
> - 한 일:
> - 검증: (실행한 명령과 결과)
> - 결정 / 발견:
> - 다음 작업자에게: (남은 일, 주의점)
> ```

## 현재 상태

- 설계: `docs/superpowers/specs/2026-09-28-flight-friend-v2-design.md` (합의 완료)
- 구현 계획: `docs/superpowers/plans/2026-09-28-flight-friend-v2-m1.md` (M1, 17 tasks)
- M1 완료: PR #62 머지·배포 (2026-09-29), OCI에서 자동 추적 정상 확인. Task 17(V1 은퇴) 코드 작업 완료 — V1 코드는 커밋 `d8e0422` (태그는 생략 — 필요하면 `git tag v1-final d8e0422`로 나중에).
- **사용자 서버 작업 (Task 17 머지 후):** `pg_dump` 백업 → `scripts/v1_freeze.sql` 실행, 1회 `docker compose --profile full up -d --remove-orphans`로 mcp/redis 컨테이너 정리.
- M2(Naver 제공자) 완료: PR #64 머지·배포 (2026-09-30). OCI에서 Naver 편도·왕복 스냅샷 ok 확인.
- 다음 순서(사용자 결정): FE 대개편 → Skyscanner 소스 → V1 테이블 동결 → README. FE 설계: `docs/superpowers/specs/2026-09-30-flight-friend-fe-redesign-design.md` (승인), 계획: `docs/superpowers/plans/2026-09-30-flight-friend-fe-redesign.md` (9 tasks, 사용자 검토 대기).
- 작업 브랜치: `claude/dazzling-shannon-4x04v7`

---

## 2026-09-28 — Claude Code — superpowers 스킬 벤더링 + SessionStart 훅 수정

- 브랜치 / 커밋: PR #60, #61 (머지 완료), `cbe63d1`
- 한 일:
  - obra/superpowers v6.4.2 스킬 14종을 `.claude/skills/`에 벤더링 (플러그인 방식은 클라우드 세션에서 로드 안 됨).
  - SessionStart 훅 설정을 표준 형식(`hooks` 배열 중첩)으로 수정.
  - 훅이 MCP API 키를 추적 파일 `.claude/settings.json`에 쓰던 문제 → gitignore된 `.claude/settings.local.json`에 쓰도록 변경.
- 검증: 세션 스킬 목록에 14종 로드 확인, 훅 실행 시 `settings.local.json` 생성 + `git check-ignore` 확인.
- 다음 작업자에게: `flight-friend` MCP가 `mcpServers` 키로 실제 연결되는지는 미확인 (공식 위치는 `.mcp.json`).

## 2026-09-28 — Claude Code — V2 브레인스토밍 + spike + 설계 문서

- 브랜치 / 커밋: `410358f` (설계 문서)
- 한 일:
  - V1 코드 전수 조사 → V1 가격 신뢰성 문제의 코드 원인 규명 (`flight_legs` `LEAST` UPSERT, `deals.last_checked_at`=재계산 시각, 날짜별 하루 1회 이하 갱신, Top-5 저장).
  - superpowers brainstorming으로 V2 제품·UX·기술 결정 합의 (설계 문서 §2–§11).
  - Spike 스크립트(`spike_trip_search.py`, throwaway, 레포 미포함)로 OCI에서 실측: 템플릿 없는 GF `tfs` 생성 확인, GF 페이지 8–10초, Naver 0건(불능), GF 왕복 vs 편도 합 비교, V1 표시가 왜곡(+11%, p90 +33.7%).
  - 설계 문서 작성.
- 검증: OCI 실측 수치는 설계 문서 §13 부록.
- 결정 / 발견: 결정 목록은 설계 문서가 원본. 특히 Naver 수집기는 2026-08-31 이후 동작하지 않음 → M1은 GF만, Naver는 병행 spike 후 M2.
- 다음 작업자에게:
  - **V1 수집기(`scripts/collect_and_diagnose.sh`, `main.py`)를 돌리지 말 것** — `cleanup_old_data()`가 `raw_legs`를 삭제한다.
  - OCI에서 spike cron(30분 주기)이 돌고 있음. 결과는 사용자가 전달 예정.

## 2026-09-28 — Claude Code — 작업 로그 도입 + M1 구현 계획

- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (이 항목이 포함된 커밋)
- 한 일:
  - `log.md` 도입 (Claude Code / Codex 교대 작업용 공용 로그).
  - superpowers writing-plans로 M1 구현 계획 작성: `docs/superpowers/plans/2026-09-28-flight-friend-v2-m1.md` — 17 tasks (백엔드 1–11, 프론트 12–15, 배포 16, V1 은퇴 17[사용자 게이트]).
- 검증: 계획 자체 검토(스펙 커버리지, 타입·시그니처 일관성, Review Focus 테스트 배치). 코드 변경 없음.
- 결정 / 발견: V2 코드는 새 패키지 `flight_friend/`에 작성, V1은 Task 17 전까지 그대로 둔다. 잠정 상수는 `flight_friend/config.py` 한 곳.
- 다음 작업자에게: 사용자 계획 승인 + 실행 방식 선택 후 Task 1 시작. 각 task는 Interfaces 블록만 보고 독립 수행 가능하도록 작성됨.

## 2026-09-28 — Claude Code — Task 1: V2 패키지 골격 · 타입 · 스키마

- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (이 항목이 포함된 커밋)
- 한 일:
  - `flight_friend/` 패키지 신설: `config.py`(잠정 상수), `types.py`(`Preferences`/`Trip`/`Run`/`LegQuote`/`RtQuote`/`ProviderResult`/`Snapshot` 데이터클래스), `db.py`(`get_conn()` — `flight_monitor.storage.get_conn`과 동일 패턴, `init_schema()` — 스펙 §9.3의 6개 테이블을 `CREATE TABLE IF NOT EXISTS`로 멱등 생성).
  - `tests/v2/` 신설: `conftest.py`(autouse `v2_db` 픽스처 — `init_schema()` 후 yield, 종료 시 6개 테이블 TRUNCATE), `test_db.py`(스키마 멱등성 + FK CASCADE 검증).
  - 컨트롤러 재정 사항 반영: `alerts.trip_id` nullable(ops 알림), `snapshots.direction` nullable(왕복 스냅샷), `trips.origin`/`adults`/`cabin` 기본값, `Preferences` 리스트 필드는 `field(default_factory=list)`, `Preferences.from_dict`는 JSON 라운드트립(튜플→리스트) 및 빈 dict를 모두 수용.
- 검증:
  - RED: `DATABASE_URL=... pytest tests/v2/test_db.py -v` → `ModuleNotFoundError: No module named 'flight_friend'` (conftest 임포트 단계에서 실패).
  - GREEN: `DATABASE_URL=... pytest tests/v2 -v` → `2 passed`.
  - 전체 스위트: `DATABASE_URL=... pytest tests/ -v` → `91 passed`(V1 베이스라인 89 + V2 신규 2, V1 무변경 확인).
  - `ruff check flight_friend tests/v2` → clean (1건 `UP035` typing.Generator→collections.abc.Generator 수정 후 통과).
  - `Preferences.to_dict()`→`json.dumps`→`json.loads`→`from_dict()` 라운드트립 및 `from_dict({})` 별도 스크립트로 수동 검증 (동일성 확인).
- 결정 / 발견:
  - 기존 V1 테스트들처럼 `tests/v2/` 아래 파일에서도 `sys.path.insert(0, ...)`로 프로젝트 루트를 직접 추가해야 임포트가 됨 (레포에 패키지 설치/`pyproject.toml` 없음, top-level `conftest.py`도 없음). `tests/v2/conftest.py`와 `tests/v2/test_db.py` 양쪽에 추가.
  - 인덱스 4개(`search_runs(status, requested_at)`, `snapshots(trip_id, observed_at)`, `leg_quotes(snapshot_id)`, `rt_quotes(snapshot_id)`)와 `alerts(trip_id, kind, sent_at)` 모두 브리프 지시대로 생성. 모든 FK `ON DELETE CASCADE`.
- 다음 작업자에게: Task 2로 진행. `snapshots`/`leg_quotes`/`rt_quotes`는 append-only이므로 UPDATE 로직을 넣지 말 것(스펙 §9.3). 단 `trips`(prefs/tracking/target_price 수정)와 `search_runs`(status 전이)는 이후 task에서 정상적으로 UPDATE 대상이다.

## 2026-09-28 — Claude Code — Task 2: Repository — trips · runs

- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (이 항목이 포함된 커밋)
- 한 일:
  - `flight_friend/repo.py` 신설: `create_trip`/`get_trip`/`list_trips`/`update_trip`(prefs·tracking·target_price 부분 수정, `clear_target`으로 NULL 지정), `enqueue_run`/`get_run`/`latest_run`, `claim_next_run`(`FOR UPDATE SKIP LOCKED`로 가장 오래된 `queued` 1건을 `running`+`started_at=now()`로 전이 후 반환), `finish_run`, `expire_stuck_runs`(`running` && `started_at < now()-older_than` → `error`), `has_open_run`(`queued`/`running` 존재 여부).
  - `RealDictCursor` → dataclass 변환 헬퍼 2개(`_row_to_trip`, `_row_to_run`)로 공통화.
  - `tests/v2/test_repo_trips_runs.py` 신설 (14 케이스): prefs 왕복(`out_dep_window` 튜플 복원 포함), `list_trips` 출국일 정렬, `update_trip` 부분 수정(prefs만 바꿔도 tracking 유지) + target_price 수정/해제, run 생성·조회·`latest_run`, `claim_next_run` FIFO·단일 처리·큐 소진 시 `None`, `finish_run`, `expire_stuck_runs`(11분 전으로 강제 UPDATE 후 만료 확인 + 최근 건은 미만료), `has_open_run` 상태 전이별 확인.
- 검증:
  - RED: `DATABASE_URL=... pytest tests/v2/test_repo_trips_runs.py -v` → `ImportError: cannot import name 'repo' from 'flight_friend'` (collection error).
  - GREEN: `DATABASE_URL=... pytest tests/v2/test_repo_trips_runs.py -v` → `14 passed`.
  - `DATABASE_URL=... pytest tests/v2 -v` → `18 passed`.
  - 전체 스위트: `DATABASE_URL=... pytest tests/ -v` → `107 passed`(기존 93 + 신규 14, V1 무변경 확인).
  - `ruff check flight_friend tests/v2` → clean.
- 결정 / 발견:
  - `create_trip`은 브리프 시그니처대로 `destination`/`out_date`/`ret_date`/`prefs`/`target_price`만 받고, `origin`/`adults`/`cabin`은 스키마 기본값(`'ICN'`/`1`/`'economy'`)에 위임.
  - `update_trip`의 SET절은 전달된 인자만 동적으로 조립(빈 경우 UPDATE 미실행) — `prefs`만 넘겨도 `tracking` 등 다른 컬럼은 그대로 유지됨을 테스트로 확인.
  - `expire_stuck_runs`는 만료 시 `finished_at=now()`도 함께 기록(`finish_run`과 동일한 종료 시맨틱 유지) — 브리프에 명시되진 않았으나 "종료된 run은 finished_at을 가진다"는 기존 일관성에 맞춤.
- 다음 작업자에게: Task 3으로 진행. `search_runs.status`는 `'queued'→'running'→'done'|'error'` 전이만 이 레포 함수들로 이루어지므로, 이후 task에서 직접 SQL로 status를 건드리지 말 것.

## 2026-09-28 — Claude Code — Task 3: Repository — snapshots · quotes · alerts · admin

- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (이 항목이 포함된 커밋)
- 한 일:
  - `flight_friend/repo.py`에 추가: `save_snapshot`(snapshot 1행 INSERT 후 `execute_values`로 `leg_quotes`/`rt_quotes` 일괄 INSERT, `card_count = len(result.legs) + len(result.rts)`, 한 커넥션/트랜잭션), `load_snapshots`(trip_id 기준, `since` 옵션 필터, `observed_at` 오름차순, 각 snapshot에 legs/rts 채워 반환), `record_alert`/`last_alert`(컨트롤러 재정에 따라 `trip_id: int | None` — `None`은 전역 ops 알림, `trip_id IS NULL`로 매칭), `recent_runs`(run + trip destination + 스냅샷 요약 목록, `requested_at DESC`), `provider_stats`(`observed_at`을 KST로 변환한 날짜 단위 GROUP BY, `days` 윈도로 필터, provider별 ok/empty/blocked/error 카운트).
  - row→dataclass 헬퍼 2개(`_row_to_leg`, `_row_to_rt`) 기존 패턴에 맞춰 추가.
  - `tests/v2/test_repo_snapshots.py` 신설 (6 케이스): `test_save_and_load_snapshot_with_quotes`(LegQuote 2건·RtQuote 1건 저장 후 `flight_numbers` 리스트 포함 동일 값 복원), `test_load_snapshots_since_filter`, `test_error_snapshot_has_no_quotes`(status `error`, legs/rts 0, card_count 0), `test_last_alert_returns_latest`(trip 알림과 전역 ops 알림이 서로 섞이지 않음도 확인), `test_provider_stats_counts_by_status`(days 윈도 밖 스냅샷 미포함 확인), `test_recent_runs_includes_snapshot_summaries`(브리프 필수 케이스 외 컨트롤러 재정 2번 커버용으로 추가).
- 검증:
  - RED: `DATABASE_URL=... pytest tests/v2/test_repo_snapshots.py -v` → `6 failed` (`AttributeError: module 'flight_friend.repo' has no attribute 'save_snapshot'` 등, 구현 전 전원 AttributeError).
  - GREEN: `DATABASE_URL=... pytest tests/v2/test_repo_snapshots.py -v` → `6 passed`.
  - `DATABASE_URL=... pytest tests/v2 -v` → `24 passed`.
  - 전체 스위트: `DATABASE_URL=... pytest tests/ -v` → `113 passed`(기존 107 + 신규 6, V1/기존 V2 무변경 확인).
  - `ruff check flight_friend tests/v2` → clean (`ruff check --fix`로 import 정렬 1건·`datetime.UTC` 별칭 7건 자동 수정 후 통과, 재실행으로 테스트 무변경 확인).
- 결정 / 발견:
  - 컨트롤러 재정 1: `record_alert`/`last_alert`는 브리프의 `trip_id: int`가 아니라 `trip_id: int | None`로 구현(스키마상 `alerts.trip_id`는 이미 nullable). `trip_id IS NULL`은 `= NULL`이 되지 않으므로 분기 처리.
  - 컨트롤러 재정 2: `recent_runs`는 제안된 row shape(`{id, trip_id, destination, trigger, status, requested_at, started_at, finished_at, snapshots: [...]}`)를 그대로 사용. run당 별도 쿼리로 snapshots를 채움(브리프에 배치 최적화 요구 없음, run 개수는 `limit` 기본 50으로 소규모).
  - 컨트롤러 재정 4: `card_count`는 `len(result.legs) + len(result.rts)`로 저장(브리프에 다른 지시 없음), `error`는 `result.error` 그대로 저장.
  - `provider_stats`는 `observed_at AT TIME ZONE 'Asia/Seoul'`로 KST 변환 후 `::date`로 날짜 추출해 GROUP BY(컨트롤러 재정 3). `days` 윈도는 `now() - (%s || ' days')::interval`로 파라미터화.
  - **[Fix round 1]** `load_snapshots`/`recent_runs`의 legs/rts(또는 snapshots) 조회는 최초 구현에서 snapshot/run당 개별 쿼리(N+1)였으나, 리뷰 지적(트립이 몇 주간 최대 시간당 수집 시 1000+ snapshots → 매 페이지 로드마다 수천 개 순차 라운드트립)에 따라 `WHERE snapshot_id = ANY(%s)`/`WHERE run_id = ANY(%s)`로 로드된 id 전체에 대해 각 1회 쿼리 후 Python에서 dict로 그룹핑하는 방식으로 수정(snapshot/run별 순서는 `ORDER BY id ASC` + 원본 순서 유지로 보존). `test_load_snapshots_attaches_quotes_to_correct_snapshot`(여러 snapshot의 quote가 서로 섞이지 않고 올바른 snapshot에 붙는지 검증) 추가.
- 다음 작업자에게: Task 4로 진행. `snapshots`/`leg_quotes`/`rt_quotes`/`alerts`는 계속 append-only이므로 UPDATE 로직 추가 금지. `recent_runs(limit=3)`의 snapshots 배열(provider/kind/direction/status)은 워커에서 GF 편도 연속 실패 감지에 쓰일 예정이니 필드명 변경 시 주의.

## 2026-09-28 — Claude Code — Task 4: 항공사 정규화 · 항공편 식별키

- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (이 항목이 포함된 커밋)
- 한 일:
  - `flight_friend/providers/__init__.py` 신설(빈 패키지 마커).
  - `flight_friend/providers/airlines.py` 신설: `normalize_airline(name)`(대소문자 무시·공백 전부 제거 후 사전 조회, 모르면 `None`), `airline_iata(name, flight_numbers)`(편명 있으면 첫 편명에서 캐리어 코드 추출 — `"RS 727"` → `"RS"`, 정확히 영숫자 2자일 때만 채택, 아니면 이름으로 폴백 → 이름 정규화 실패 시 `"?" + 공백 제거한 name"`), `flight_key(date_, dep_airport, arr_airport, dep_time, arr_time, stops, airline)`(`"YYYY-MM-DD|DEP|ARR|dep_time|arr_time|stops|airline"`, `stops is None`이면 `"?"`).
  - 매핑 사전(`_AIRLINE_IATA`)에 V1 `collector_google_flights._AIRLINE_IATA` 전체(V1 파일은 무변경, 값만 복사) + 브리프 §13 실측 표기 차이 12쌍 전부 반영. `한 에어 시스템`은 의도적으로 매핑하지 않음(발권사이지 운항사가 아니므로).
  - `tests/v2/test_airlines.py` 신설(8 케이스): `test_normalize_variants`(12쌍 전부 양쪽 표기가 동일 코드로 정규화되는지), `test_normalize_unknown_returns_none`(`한 에어 시스템` 포함), `test_airline_from_flight_number_wins`, `test_airline_iata_falls_back_to_name_when_no_flight_number`, `test_airline_iata_falls_back_to_unknown_marker`, `test_flight_key_without_flight_number`(서로 다른 미지 항공사가 다른 키로 끝나는지), `test_flight_key_format`, `test_flight_key_stops_none_becomes_question_mark`.
- 검증:
  - RED: `DATABASE_URL=... pytest tests/v2/test_airlines.py -v` → `ModuleNotFoundError: No module named 'flight_friend.providers.airlines'` (collection error, 8건 전부 수집 실패).
  - GREEN: `DATABASE_URL=... pytest tests/v2/test_airlines.py -v` → `8 passed`.
  - 전체 스위트: `DATABASE_URL=... pytest tests/ -q` → `122 passed`(기존 114 + 신규 8, V1/기존 V2 무변경 확인).
  - `ruff check flight_friend tests/v2` → 최초 실행 시 `F601`(딕셔너리 키 `"티웨이항공"` 중복 리터럴, V1 매핑과 §13 매핑 양쪽에 존재) 지적 → §13 쪽의 중복 항목 제거 후 재실행 clean.
- 결정 / 발견:
  - `airline_iata`의 편명 캐리어 코드 검증은 "공백 이전 부분이 영숫자 정확히 2자"만 채택(정규식 `^[0-9A-Za-z]{2}$`) — 그 외(3자 이상, 특수문자 등)는 무시하고 이름 기반 폴백으로 떨어짐. 브리프 §Controller notes 그대로.
  - `normalize_airline`은 키/입력 양쪽에 `"".join(s.lower().split())`를 적용해 사전을 조회 시점에 매번 정규화하지 않도록 모듈 로드 시 `_NORMALIZED_AIRLINE_IATA`를 미리 빌드.
  - 본 모듈은 실패를 항상 `?`-접두 미지 키(고유값)로 떨어뜨려 서로 다른 미지 항공사가 절대 같은 `flight_key`로 병합되지 않게 함 — 오매칭보다 중복을 택하는 태스크 원칙 준수.
- 다음 작업자에게: Task 5로 진행. V1 `_AIRLINE_IATA`는 이 커밋에서 손대지 않았음(그대로 유지, V1은 Task 17에서 은퇴 예정). `flight_friend/providers/airlines.py`의 매핑 사전에 새 항공사 표기를 추가할 때도 동일 IATA 코드에 중복 키 리터럴이 생기지 않도록 주의(ruff `F601`).

## 2026-09-28 — Claude Code — Task 5: Google Flights 어댑터

- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (이 항목이 포함된 커밋)
- 한 일:
  - `flight_friend/providers/google_flights.py` 신설:
    - `build_oneway_url(dep, arr, date_)`/`build_roundtrip_url(dep, arr, out_date, ret_date)` — 템플릿 없이 protobuf `tfs`를 직접 생성(스펙 §5.2/§13). outer 필드(`1:28,2:2,3:<FlightData>…,8:1,9:1,14:1,16:{08 ff×9 01},19:<2 편도|1 왕복>`)·FlightData(`2:date,13:{1:1,2:dep},14:{1:1,2:arr}`)는 스펙 부록의 실측 tfs(`CBwQAhoe…`)를 바이트 단위로 역산해 검증 후 그대로 구현. 왕복은 FlightData 2건(출국 dep→arr, 귀국 arr→dep)을 필드3에 반복.
    - `build_booking_url(card, dep, arr, date_str)` — V1 `_build_booking_tfs`/`_build_booking_url`을 그대로 이전(로직 무변경, 이름만 `_build_booking_url`→`build_booking_url`로 공개).
    - `extract_js()`/`parse_cards(html)` — V1 `_extract_js`/`_parse_flight_cards` 그대로 이전.
    - `make_scroll_js()` — V1 `crawler_utils.make_scroll_js` 그대로 이전.
    - `cards_to_legs(cards, date_, dep, arr, search_url)` — 카드별 `airline_iata(card["airline"], card["flight_numbers"])`로 항공사 결정, dep/arr 공항은 카드 값 우선·없으면 인자로 폴백, `dep_time`/`arr_time` 없는 카드는 skip, `flight_key`로 dedupe(동일 키면 최저가 유지), 가격 오름차순 반환.
    - `cards_to_rts(cards, out_date, dep, arr)` — 왕복 페이지 카드(가격=왕복 총액)를 출국편 `flight_key`로 동일하게 dedupe·정렬.
    - `search_oneway(crawler, dep, arr, date_)`/`search_roundtrip(crawler, dep, arr, out_date, ret_date)` — 브리프 §9.2 시그니처 그대로(추가 인자 없음). `time.perf_counter()`로 `seconds` 측정, `CrawlerRunConfig`는 `_default_config()` 안에서 import. 카드>0→`ok`, 카드 0 + HTML에 `unusual traffic`/`sorry/index`/`recaptcha`(대소문자 무시)→`blocked`, 카드 0→`empty`, `arun` 예외 또는 `result.success=False`→`error`(메시지 보존). `captcha` 단독 문자열은 차단 판정에 쓰지 않음(스펙 §9.2 — 정상 페이지에도 존재).
  - `tests/v2/fixtures/gf_cards.html` 신설 — `<div id="__fl__">` JSON, ICN→FUK 2026-10-21 카드 4건(에어서울/제주항공/진에어×2, 진에어 카드는 완전 중복).
  - `tests/v2/test_google_flights.py` 신설(6 케이스, 브리프 Step1 그대로): URL 구조(base64 디코드해 날짜/공항/trip-type 바이트 직접 확인), 왕복 2-leg+trip=1, fixture 파싱(4건), dedupe(진에어 중복 2장→1건), 가격순 정렬+편명 기반 IATA, status 매핑(ok/blocked/empty/error, `captcha` 단독은 empty로).
- 검증:
  - RED: `flight_friend/providers/google_flights.py`를 임시로 빼고 `DATABASE_URL=... pytest tests/v2/test_google_flights.py -v` → `ModuleNotFoundError: No module named 'flight_friend.providers.google_flights'`(collection error, 6건 전부 수집 실패).
  - GREEN: 복원 후 동일 명령 → `6 passed`.
  - 전체 스위트: `DATABASE_URL=... pytest tests/ -q` → `128 passed`(기존 122 + 신규 6, V1/기존 V2 무변경 확인). [Fix round 1] 테스트 1건 추가 후 `129 passed`.
  - `ruff check flight_friend tests/v2` → clean.
  - 별도 수동 확인: fixture로 `search_roundtrip`도 fake crawler로 실행해 `status="ok"`, `rts` 3건(중복 dedupe 반영) 생성 확인(브리프 Step1엔 없지만 왕복 경로 자체가 안 죽는지 점검용).
- 결정 / 발견:
  - **crawl4ai 미설치 환경에서 status-mapping 테스트를 어떻게 통과시킬지 [Fix round 1로 수정됨]**: 최초 구현은 `search_oneway`/`search_roundtrip`에 선택적 `config` 인자를 추가해 테스트가 `CrawlerRunConfig` import를 우회하게 했다. 이 방식은 브리프가 요구한 게 아니라 디스패치 노트의 제안이었고, Task 10(워커)이 브리프 그대로의 시그니처(`crawler, dep, arr, date_`)를 소비하므로 리뷰에서 지적되어 컨트롤러 재정으로 제거했다. 현재(수정 후) 방식: 공개 시그니처는 `config` 없이 브리프 그대로 유지하고, crawl4ai 없이 상태 분기만 검증하려는 테스트는 `monkeypatch.setattr(google_flights, "_default_config", lambda: <fake config>)`로 내부 헬퍼를 직접 대체한다(`test_status_mapping`). 별도로 monkeypatch 없이 실제 `_default_config()` → `ImportError` → `status="error", error="crawl4ai not installed", seconds=0.0` 경로를 검증하는 `test_search_oneway_errors_when_crawl4ai_missing`을 추가해, 이 프로젝트 테스트 venv에 crawl4ai가 실제로 없는 상태에서 그 경로가 동작함을 자동으로 확인한다.
  - outer/FlightData protobuf 필드 값은 브리프 문구뿐 아니라 프롬프트에 인용된 실측 tfs(`CBwQAhoeEgoyMDI2LTEwLTIxagcIARIDSUNOcgcIARIDU0hJQAFIAXABggELCP___________wGYAQI`)를 직접 base64 디코드해 바이트 단위로 역산·대조(필드19 tag가 2바이트 varint(`\x98\x01`)이고 값 `\x02`=편도인 것까지 확인) — 브리프 §5.2 문구와 실측이 정확히 일치함을 재확인 후 구현.
  - `cards_to_rts`는 브리프에 dedupe 명시가 없었지만(§9.2엔 "출국편 키로"만 명시) `cards_to_legs`와 동일하게 `flight_key` 기준 최저가 dedupe + 가격 오름차순 정렬을 적용 — 왕복 페이지도 동일 카드 중복 추출 현상(스펙 §13 "SHI 각 1, 페이지 내 중복 추출 존재")이 있을 수 있어 방어적으로 일관 처리. 필요하면 다음 task에서 재정 가능.
  - `Crawler`/`CrawlResult`는 `typing.Protocol`로 정의(브리프 지시대로 `Any` 미사용). `_classify`는 `Literal["ok","blocked","empty"]`를 반환하도록 타입해 `ProviderResult(status=...)` 호출부의 `# type: ignore[arg-type]` 2건을 제거(Fix round 1).
- 다음 작업자에게: Task 6으로 진행. `search_oneway`/`search_roundtrip`는 브리프 §9.2 시그니처 그대로(`crawler, dep, arr, date(s)`, 추가 인자 없음) — Fix round 1에서 최초의 선택적 `config` 인자를 제거했으니 이 함수들을 호출/재정의할 때 그 인자가 없다고 가정할 것. `build_booking_url`은 V1과 동일하게 편명 정규식이 매치 안 되거나 `segment_airports` 길이가 안 맞으면 `None`을 반환(그대로 유지).

## 2026-09-29 — Claude Code — Task 6: 도메인 — 갱신 스케줄
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(v2): refresh schedule rules`
- 한 일: `flight_friend/domain/schedule.py` (refresh_interval, freshness_window, days_to_departure, is_due, cooldown_remaining) + `tests/v2/test_schedule.py`. 이전 구현자가 남긴 미커밋 파일을 검토해 유지하고 `__init__.py`와 테스트 3건(주기 경과, archived, KST 날짜 경계) 추가, ruff 지적 2건 수정.
- 검증: schedule.py 없이 pytest → ModuleNotFoundError(RED), 복구 후 12 passed. 전체 `pytest tests` 141 passed, ruff clean.
- 결정 / 발견: 티어 값(6h/2h/1h, 60/14일)은 모듈 상수로 분리(잠정치, 실측 후 재조정). is_due의 "오늘"은 now를 Asia/Seoul로 변환한 날짜. MANUAL_COOLDOWN은 config에서 import.
- 다음 작업자에게: Task 7 진행.

## 2026-09-29 — Claude Code — Task 7: 도메인 — 현재 편도 병합 · 선호 조건 · 조건 밖 힌트
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7`, feat(v2): current leg merge, preferences and near-miss hint
- 한 일: `flight_friend/domain/results.py` 추가 — `current_legs`(제공자·방향별 최신 ok 편도 스냅샷만, flight_key 병합, stale 제외 best), `violations`, `near_miss`. 테스트 16개(`tests/v2/test_results_legs.py`).
- 검증: `pytest tests -q` 전체 통과, `ruff check flight_friend tests/v2` clean.
- 결정 / 발견: stale은 `observed_at < now - window`(경계는 fresh). 병합 대표 leg는 최저가 제공자(동가면 제공자명 사전순). near_miss는 조건 내 반대 방향 최저가가 있는 방향만 후보. `max_price`는 Task 8.
- 다음 작업자에게: Task 8이 같은 `results.py`에 조합 함수를 추가한다.


## 2026-09-29 — Claude Code — Task 8: 도메인 — 조합 · 파레토 대표 후보 · 왕복 참고가
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7`, feat(v2): combos, pareto candidates and round-trip reference
- 한 일: `flight_friend/domain/results.py`에 `stay_minutes`, `Candidate`, `in_condition`, `pareto_candidates`, `cheapest_combo`, `RtReference`, `rt_reference` 추가. 테스트 12개(`tests/v2/test_results_combos.py`).
- 검증: 구현 전 pytest → ImportError(RED), 구현 후 12 passed. 전체 `pytest tests` 169 passed, ruff clean.
- 결정 / 발견: 파레토 limit 초과 시 첫·끝 고정 + 가격 균등 목표에 가장 가까운 미선택 항목(동률이면 저가 쪽). rt_reference는 W 밖 스냅샷 무시(`observed_at < now - window`), 편도 합은 주어진 모든 편(조건 무관)의 항공사별 최저가. 시각 계산은 naive datetime(현지 시각).
- 다음 작업자에게: Task 9 진행.

## 2026-09-29 — Claude Code — Task 9: 도메인 — 추적 값 · 통계 · 알림 판정
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7`, feat(v2): tracking series, stats and alert rules
- 한 일: `flight_friend/domain/tracking.py` 추가 — `run_values`(run별 스냅샷만, W 무시), `daily_series`(KST 날짜별 최저), `tracking_stats`, `should_alert_new_low`, `should_alert_target`. 테스트 14개(`tests/v2/test_tracking.py`).
- 검증: 구현 전 pytest → ModuleNotFoundError(RED), 구현 후 14 passed. 전체 `pytest tests` 183 passed, ruff clean.
- 결정 / 발견: 알림 임계는 `drop >= ALERT_DROP_KRW or drop >= ALERT_DROP_PCT * reference` 공통 함수. 하루 최저 combo 동률이면 먼저 관측된 run의 partial 사용. new_low의 이전 최저는 `series[:-1]`(마지막 = 오늘).
- 다음 작업자에게: Task 10 진행. `current`는 호출자가 Task 7/8로 W를 적용해 계산해서 넘겨야 한다.

## 2026-09-29 — Claude Code — Task 10: search-worker
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7`, feat(v2): search worker with scheduler and alerts
- 한 일: `flight_friend/worker.py` 추가 — `execute_run`(oneway out/in + roundtrip을 gather 동시 실행, 스냅샷 3개 저장, 예외 시 error), `schedule_due_trips`, `evaluate_alerts`(new_low/target, 발송 성공 시에만 record_alert), `evaluate_ops`(최근 3 run GF oneway 전부 비ok, 6시간 쿨다운), `main_loop`(crawl4ai는 함수 내부 import, 반복마다 예외 로깅 후 계속). `domain/tracking.py`에 `current_value` 추가. 테스트 `tests/v2/test_worker.py` 9개 + tracking 1개.
- 검증: 구현 전 pytest → ModuleNotFoundError(RED), 구현 후 통과. 전체 `pytest tests` 통과, `ruff check flight_friend tests/v2` clean, crawl4ai 없이 `import flight_friend.worker` 성공.
- 결정 / 발견: 알림 메시지 끝에 공백 + `/trips/{id}`. new_low 퍼센트는 `series[:-1]` 최저 대비. `main_loop`은 테스트하지 않음(1분 주기 유지보수는 monotonic 시계).
- 다음 작업자에게: `flight_monitor.notifier.send_alert`는 Task 17에서 이동 예정. Task 11 진행.


## 2026-09-29 — Claude Code — Task 11: API — views · 엔드포인트
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / feat(v2): trip API and views
- 한 일: `flight_friend/api/{views,main}.py` — views(Service, dict 빌드, FastAPI 무의존) + main(Router, 검증/에러 매핑). `httpx` requirements 추가. `tests/v2/test_api.py` 17개.
- 검증: `pytest tests/v2` 121 passed, `pytest tests` 210 passed, ruff clean.
- 결정 / 발견 (프론트 types.ts 기준 JSON, 날짜/시각은 ISO 문자열, 시각은 aware — DB 세션 tz라 +09:00일 수 있음):
  - `GET /api/trips` → `[{id, destination, out_date, ret_date, days_to_departure, tracking, current, current_observed_at, change_vs_start_pct, archived}]`
  - `POST /api/trips` → 201 `{id, run_id}`; 422(코드 `^[A-Z]{3}$`, ret>out, out>=KST 오늘). body `{destination, out_date, ret_date, prefs?, target_price?}`
  - `GET/PATCH /api/trips/{id}` → `{trip:{id, origin, destination, out_date, ret_date, adults, cabin, prefs, target_price, tracking, archived, days_to_departure, created_at}, run:{id,status,requested_at}|null, providers:[{provider,status,observed_at,last_ok_at}], stats:{current,start,start_day,low,low_day,median,days,comparable}, legs:{out:[MergedLegView],in:[...]}, candidates:[{out_flight_key,in_flight_key,price,stay_min}], near_miss:{direction,flight_key,violated,combo_price,saving}|null, rt_reference:[{airline_iata,rt_min,ow_sum,diff}], window_minutes}`
  - `MergedLegView` = `{flight_key, dep_time, arr_time, airline_name, airline_iata, flight_numbers, stops, duration_min, dep_airport, arr_airport, best_price, best_provider, in_condition, violations, prices:[{provider,price,observed_at,booking_url,stale}]}`
  - PATCH body `{prefs?, tracking?, target_price?}`: `target_price: null`=해제, 생략=유지. prefs는 통째 교체(`Preferences.to_dict()` 형태, window는 `[from,to]`).
  - `POST /api/trips/{id}/runs` → 202 `{run_id}` (열린 run 있으면 그 id) / 429 `{retry_after_seconds}`
  - `GET /api/runs/{id}` → `{id, status, snapshots:[{provider,kind,direction,status}]}`
  - `GET /api/trips/{id}/history` → `[{day,combo,out_min,in_min,partial}]`
  - `GET /api/admin/runs` → recent_runs(시각 ISO), `GET /api/admin/providers?days=7` → `[{provider,day,total,ok,empty,blocked,error}]`
  - `GET /healthz`; 비-API 경로는 `flight_front/web/dist` SPA fallback (dist 없으면 미등록).
- 다음 작업자에게: 프론트(Task 12~)는 위 형태를 `types.ts`로. 알 수 없는 id는 404. `prices[].stale`이면 best_price 제외됨(전부 stale이면 best_price null).

## 2026-09-29 — Claude Code — Task 12: 프론트 — 앱 셸 · Trip 목록 · 새 Trip
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7`, `feat(v2-web): app shell, trip list and new trip form`
- 한 일:
  - V1 컴포넌트 삭제(ThemeToggle·PriceChart만 유지), `types.ts`/`api.ts`/`utils.ts`를 V2 전용으로 재작성 (`formatWon` 추가, `STALE_HOURS`·`normalizeTime` 제거).
  - `pages/TripList.tsx`, `pages/NewTrip.tsx` 신규, `App.tsx` 라우트: `/`, `/trips/new`, `/trips/:id`(placeholder), `/admin`(placeholder). 내비는 브랜드 + "새 여행"만.
- 검증: `npm run build` 통과; uvicorn :8765 + headless Chromium으로 SPA 렌더(목록 행·새 여행 폼) 확인, 390px iframe에서 가로 스크롤 없음; curl로 trip 생성/목록/422 확인; `pytest tests/` 211 passed.
- 결정 / 발견: PriceChart가 V1 `fetchPriceHistory`/`PriceHistoryPoint`에 의존해 tsc 통과를 위해 이 둘만 V1 잔재로 유지 (Task 13에서 PriceChart 교체 시 제거). vite dev proxy는 8000 그대로.
- 다음 작업자에게: Task 13에서 `/trips/:id` 상세 구현, `types.ts`의 V1 잔재 두 타입과 `api.ts`의 `fetchPriceHistory` 제거.

## 2026-09-29 — Claude Code — Task 13: 프론트 — Trip 화면: 상태 헤더 · 확인 버튼 · 추적 요약 · 차트
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(v2-web): trip status header, run polling and tracking summary`
- 한 일: `TripPage`(trip/run 상태 소유, 2.5초 폴링, done/error 시 getTrip 1회 재조회로 일괄 교체, 429 쿨다운 카운트다운), `StatusHeader`, `TrackingSummary`, `HistoryChart`(기본 접힘·선 토글·partial 속 빈 점), `providers.ts`; App 라우트 연결; V1 잔재(`PriceChart.tsx`, `fetchPriceHistory`, `PriceHistory*` 타입) 삭제.
- 검증: `npm run build` 통과. 실제 API + headless Chromium(390px)로 헤더/요약/차트 토글/버튼(429 쿨다운 → queued 진행 표시 → DB에서 run 완료 → 결과 교체) 확인, 가로 스크롤 없음. `pytest tests/` 211 passed.
- 결정 / 발견: `dday`를 utils.ts에 추가(TripList의 로컬 복사본은 그대로 둠). 개발 DB의 trips를 TRUNCATE 후 스모크용 2건 시드.
- 다음 작업자에게: Task 14는 TripPage에 결과 컴포넌트를 추가 (`trip` 상태 + setTrip 전달). 빈 상태 진행 표시(`RunProgress`)는 TripPage 안에 있음.

## 2026-09-29 — Claude Code — Task 14: 프론트 — Trip 화면: 결과 영역
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(v2-web): trip results, candidates and selection bar`
- 한 일: `FilterBar`(prefs 편집 -> `patchTrip` 전체 prefs, 400ms 디바운스/토글 즉시), `Candidates`, `NearMissHint`, `LegList`, `LegCard`, `SelectionBar`, `Results`, `TripPage`(선택 상태 소유·TripView 교체 시 유지), `utils.stayMinutes/formatStay`, `HistoryChart` refreshKey 재조회(Task 13 리뷰 이월).
- 검증: `npm run build` 통과, `pytest tests/` 211 passed. 브라우저(headless Chromium, 실제 API, FUK급 시드 출국 40/귀국 35): 필터 변경 즉시 반영(재검색 없이 PATCH만), 후보 클릭 선택 동기화, near-miss 문구 + [보기], 모바일 390px 탭·가로 스크롤 없음, 선택 바 합계/체류/예약 링크/rt 줄(저렴), 차트 refetch. 코드 읽기로만 확인: stale `오래됨`·`확인가 없음` 카드, rt `비쌈`, 예약 URL null 숨김, 다크 모드.
- 결정 / 발견: `NearMissView.violated`는 문자열 하나(백엔드 그대로) — types.ts의 `string[]` 오류 수정. 편 dep/arr 시각은 ISO가 아니라 현지 "HH:MM".
- 다음 작업자에게: Task 15는 Admin 화면. 개발 DB는 비어 있음(스모크 시드 삭제).
- Task 14 Fix round 1: FilterBar 언마운트/trip 전환 시 in-flight PATCH 무효화(seq++) + TripPage onApplied trip id 가드, `RtReference.ow_sum/diff` nullable, LegCard 선택 영역을 `<button aria-pressed>`로(▾ 별도 버튼), 선택 유지 양쪽 독립. build 통과, 브라우저에서 후보 선택·Enter/Space 선택 확인(키 소실 독립 폴백은 코드로만).

## 2026-09-29 — Claude Code — Task 15: 프론트 — /admin
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / feat(v2-web): admin runs and provider health
- 한 일: `pages/Admin.tsx` 추가(최근 실행 표 + 제공자별 일자 성공률, 7/14/30일 선택, 새로고침), App.tsx의 `/admin` 자리표시자 교체(내비 미노출). `types.ts`의 `AdminRow`를 서버 shape에 맞는 `AdminRun`/`ProviderDay`로 교체, api.ts 반환 타입 갱신.
- 검증: `npm run build` 통과; pytest 211 passed. 브라우저 확인(headless Chromium, 실제 API + 시드 데이터, 1200px/390px): 실행 표·스냅샷 배지·Trip 링크·제공자별 일자 표·기간 선택·새로고침·오류 상태·390px 가로 스크롤 없음. 코드만 읽고 확인: 로딩/빈 상태 문구, 알 수 없는 status 대체 표시, 다크 모드.
- 결정 / 발견: `recent_runs`는 snapshots.error 메시지를 내려주지 않아 실패 사유는 status(차단 의심/결과 없음/오류)까지만 표시.
- 다음 작업자에게: Task 16. 서버는 종료했고 개발 DB는 비어 있음.

## 2026-09-29 — Claude Code — Task 16: 배포 연결 · 문서
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `chore(v2): wire worker service, deploy and AGENTS.md for V2`
- 한 일: compose에 `worker` 서비스(Dockerfile.collector, profile full, 상주) 추가·app 헬스체크 `/healthz`; Dockerfile CMD → `flight_friend.api.main:app`; deploy.yml readiness를 `/healthz`로, worker를 app 헬스체크 후 빌드·기동(collector 빌드 제거); CI ruff 0.16.9 고정 + httpx 설치 + `ruff.toml`에 V1 경로 제외; 아키텍처 테스트 V2 규칙 4개; AGENTS.md V2 재작성.
- 검증: ruff 0 errors, pytest 전체, npm run build, compose config, YAML 파싱 (보고서 참고).
- 결정 / 발견: deploy의 `up -d`를 `up -d app mcp caddy`로 좁힘(전체 `up -d`는 미빌드 worker를 헬스체크 전에 인라인 빌드하게 됨). collector/mcp 서비스는 Task 17까지 유지.
- 다음 작업자에게: **사용자가 OCI에서 V1 수집 cron과 spike cron을 제거해야 한다.** 머지 시 자동 배포되며 worker가 처음 기동한다. Task 17에서 V1 코드·collector/mcp 서비스·ruff 제외 목록·`flight_monitor.notifier` 이동 처리.
- Task 16 Fix round 1: `init_schema()`를 API lifespan + worker 시작에서 호출(advisory lock), `/healthz`가 `schema_ready()` 실패 시 503, ruff `./main.py`로 V2 main 린트 복구, AGENTS.md 스키마 진입점 정정, deploy에 worker running 체크 추가. ruff 0 errors, pytest 217 passed.

## 2026-09-29 — Claude Code — 최종 리뷰 수정
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `fix(v2): classify blocked/empty GF pages...`, `fix(v2): worker run timeout...`, `fix(v2): reject inverted time windows...`, `fix(v2-web): trip settings...`
- 한 일 (최종 리뷰 항목 1~11):
  1. GF `wait_for`를 카드 OR 차단 표지 OR 결과없음 문구로 확장, 타임아웃성 `success=False`는 받은 HTML로 blocked/empty 분류(네비게이션 오류 `net::ERR_*`만 error). 결과없음 문구는 라이브 GF 미검증 추정.
  2. `run_with_timeout`(RUN_TIMEOUT 3분)으로 멈춘 크롤 차단 → run error + 크롤러 재생성. `evaluate_ops`는 finished run 최근 3건만, 스냅샷 없는 error run은 실패로 계산.
  3. Trip 페이지에 `TripSettings`(추적 on/off, 목표가 저장/비우면 해제, id 불일치 응답 무시).
  4. 추적 꺼짐/보관/지난 출국일 Trip은 `evaluate_alerts` 건너뜀.
  5. 알림에 절대 Trip URL(`PUBLIC_BASE_URL` → `https://$DOMAIN` → 상대경로), 현지 체류시간, 가는편/오는편 예약 URL 추가. compose worker env · `.env.example` 갱신.
  6. HH:MM 아닌 시각 카드 제외. 7. 검색 공항과 다른 dep/arr 카드 제외.
  8. `providers.ts` 기본 제공자에서 naver 제거. 9. 시간대 시작>끝을 API 422 + FilterBar/NewTrip 인라인 메시지로 거부.
  10. AGENTS.md `init_schema()`. 11. vite `/ws` 프록시 제거.
- 검증: ruff 0 errors, pytest 232 passed, `npm run build` 통과. 브라우저(headless Chromium, 실제 API): 항목 3(토글/목표가 저장·비우기·새로고침 유지·390px 가로 스크롤 없음)과 9의 NewTrip 메시지 확인. 코드만 읽고 확인: 항목 8, 9의 FilterBar 메시지, 항목 1의 실제 GF 동작(fake crawler 테스트만), 항목 2의 실제 브라우저 재기동(crawler.close/start), 항목 5의 실제 발송.
- 결정 / 발견: 서버 종료, 개발 DB 비어 있음.
- 다음 작업자에게: Task 17(사용자 게이트) 및 사용자의 OCI 서버 작업(V1 수집 cron·spike cron 제거). 배포 시 `.env`에 `PUBLIC_BASE_URL` 설정 권장.

## 2026-09-30 — Claude Code — Task 17: V1 은퇴
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (master `c889adf`에서 재시작) / `chore: retire V1 code (tagged v1-final)`
- 한 일:
  - V1 기준점은 V2 시작 직전 커밋 `d8e0422` (`v1-final` 태그는 사용자 결정으로 생략).
  - `flight_monitor/notifier.py` → `flight_friend/notifier.py` 이동 (V1 전용 `notify()` 제거, `send_alert` 등만 유지), 테스트는 `tests/v2/test_notifier.py`로.
  - 삭제: `main.py`, `diagnosis_agent.py`, `mcp_server.py`, `Dockerfile.mcp`, `scripts/*`(V1), `flight_monitor/`, `flight_front/api/`, `flight_front/__init__.py`, V1 테스트 8개.
  - compose에서 `collector`·`mcp`·`redis` 서비스와 app의 `/hostfs` 마운트·`REDIS_URL` 제거 (V2는 redis·hostfs 미사용). Caddyfile `/mcp` 라우트 제거, deploy.yml에서 mcp 빌드·태깅·헬스체크 제거.
  - `flight-friend` MCP 서버가 사라지므로 이를 설정하던 SessionStart 훅(`.claude/hooks/session-start.sh`)과 `.claude/settings.json` 삭제.
  - requirements에서 V1 전용 패키지(amadeus, mcp, redis, anthropic, psutil, aiofiles) 제거. `Dockerfile.collector` CMD를 worker로.
  - `ruff.toml` V1 제외 목록 삭제. 아키텍처 테스트는 V1 규칙 삭제, providers/db/repo의 웹 프레임워크 금지를 V2 규칙에 추가.
  - `scripts/v1_freeze.sql`: V1 테이블 9개 + `v_best_observed` 뷰 + `record_price_change()` 함수를 `v1` 스키마로 이동 (함수는 search_path=v1 고정). 트랜잭션, 멱등.
  - AGENTS.md / ISSUES.md / TODOS.md를 V2 기준으로 갱신.
- 검증: pytest 147 passed (V1 테스트 85개 삭제분 제외), `ruff check .` 통과, `npm run build` 통과. freeze SQL은 V1 `init_db()` + V2 `init_schema()`로 만든 임시 DB에서 실행: public에 V2 6개만 남음, v1에 9개, 재실행 오류 없음, 이동 후 `v1.flight_legs` UPDATE 시 트리거가 `v1.price_events`에 기록됨.
- 결정 / 발견: `readme.md`와 CLAUDE.md 포트폴리오는 V1 기준 서술이 남아 있음 — 갱신 여부는 사용자 결정.
- 다음 작업자에게: 서버에서 freeze SQL 실행 전 백업 필수. M2 Naver spike.
- Task 17 추가 (사용자 요청): `tests/v2/*` → `tests/`로 평탄화(`tests/fixtures/` 포함), 파일마다 있던 `sys.path.insert`를 `tests/conftest.py` 한 곳으로. autouse fixture 이름 `v2_db` → `clean_db`, `pytest.mark.no_db` 모듈은 DB 초기화를 건너뜀(`test_architecture.py`는 DB 없이 4 passed 확인). pytest 147 passed, ruff 0.16.9 clean. CI lint 실패(`notifier.py` import 순서 I001)는 로컬 ruff가 0.15.8이었던 탓 — 로컬 검증은 `python -m ruff`(0.16.9)로.

## 2026-09-30 — Claude Code — Naver spike 시작
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (master `2705921`에서 재시작) / `chore(spike): naver page and API capture script`
- 한 일: `scripts/naver_spike.py` — 편도 검색 페이지를 열어 최종 DOM·스크린샷·naver 도메인 XHR/fetch 요청과 JSON 응답을 저장하고, V1 셀렉터 적중 수·가격 텍스트 수·차단 문구·큰 JSON 응답을 요약한다. 목적: DOM 셀렉터 재작성 vs 내부 API 중 복구 경로 결정, 편명·예약 링크 확보 가능성 확인 (스펙 §11). 일회성이라 M2 계획 후 삭제.
- 검증: 이 세션에서는 네트워크 정책이 `flight.naver.com`을 막아(`ERR_TUNNEL_CONNECTION_FAILED`) 산출물 생성 경로까지만 확인. 실측은 OCI에서.
- 다음 작업자에게: 사용자의 OCI 실행 결과(`summary.txt`, `requests.jsonl`)로 경로 결정 → M2 계획.
- Naver spike 결과 (같은 날, 사용자가 세션 네트워크를 열어 줌): 내부 API `searchFlights`(SSE)를 브라우저 없이 직접 호출해 편명·시각·파트너별 요금 수신. V2 GF 파서 결과와 flight_key 40/40 일치. 예약 딥링크 없음, 조건부(카드) 요금과 코드셰어 중복 존재, 도착 시각 1분 흔들림 1건. 상세는 스펙 §13.1. `scripts/naver_spike.py`를 직접 API 프로브로 교체 (OCI 한국 IP 확인용). 세션 Chromium이 에이전트 프록시 CA를 신뢰하도록 NSS DB(`~/.pki/nssdb`)에 `/root/.ccr/agent-proxy-ca.crt` 등록함 — 새 컨테이너에서는 다시 필요.
- 다음 작업자에게: M2 설계 결정 필요 — (1) 표시 가격 기준 A01 vs 조건부 포함, (2) 코드셰어 처리, (3) 시각 흔들림 대응, (4) OCI에서 API 동작 확인.
- Naver 예약 딥링크 확인: `/detail/...&selectedFlight=1:{itineraryId}:{fareType}:HK:{항공사}:` 로 판매사 선택 페이지가 열림 (fareType 필수). 헤드리스 기본 UA에서는 Naver가 결과를 안 그림 — 데스크톱 UA 필요. 사용자 M2 결정 4건을 스펙 §13.1 끝에 기록. 다음: M2 설계.

## 2026-09-30 — Claude Code — M2 설계 (brainstorming)
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `docs: M2 Naver provider design`
- 한 일: spike 결과로 M2 설계 문서 작성. 결정: 조건 없는(A01)·조건부 가격 이중 보관, 계산은 조건 없는 가격 기준, 코드셰어 제외, 편명 보조 매칭(시각 차이는 GF 우선으로 조용히 합침), Naver 왕복 수집, API만 사용(막히면 실패로 드러냄), 견적 행에 cond_* 칸 추가, 판매사 선택 딥링크, 상세 기본 펼침 + 큰 토글(FE 대개편 예정이라 최소 변경).
- 다음 작업자에게: 사용자 설계 검토 후 writing-plans로 M2 구현 계획. 첫 task는 OCI 확인 게이트.
- M2 구현 계획 작성: 9 tasks (1 OCI 게이트 → 2 cond 칸 → 3·4 Naver 편도·왕복 → 5 병합 → 6 왕복 참고가·API → 7 worker·ops → 8 화면 → 9 마무리). 테스트 fixture `tests/fixtures/naver_oneway_icn_fuk.sse`(부분·최종 2줄, 매핑 8: 코드셰어 1·경유+sameFare 1 포함), `naver_roundtrip_icn_fuk.sse`(조합 6: 코드셰어 1)는 spike 실응답을 잘라 만듦 — 계획의 기대값이 이 파일 기준.


## 2026-09-30 — Claude Code — M2 Task 2: 조건부 가격 칸
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(m2): conditional price columns on quotes`
- 한 일: `LegQuote.cond_price/cond_label/cond_booking_url`, `RtQuote.cond_total_price/cond_label`(기본 None) 추가, `init_schema`에 `ADD COLUMN IF NOT EXISTS` 5개, `save_snapshot`/`_row_to_leg`/`_row_to_rt` 매핑, `record_alert` kind 타입 `str`로 확대. 아직 아무도 쓰지 않아 M1 동작 불변.
- 검증: `pytest tests/ -q` 150 passed, `python -m ruff check .` 통과.
- 다음 작업자에게: Task 3(Naver 편도 provider)에서 cond_* 채우기.

## 2026-09-30 — Claude Code — M2 Task 3: Naver provider (편도)
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(m2): naver provider oneway`
- 한 일: `providers/naver.py`(`search_oneway`, `build_booking_url`, `build_search_url`, 내부 `_post_search`/`_itinerary_ok`/`_fares`), `config.py`에 `NAVER_ONEWAY_TIMEOUT`(45)/`NAVER_ROUNDTRIP_TIMEOUT`(60), `tests/test_naver.py`(fixture 기반, MockTransport).
- 검증: `pytest tests/ -q` 통과, `python -m ruff check .` 통과.
- 다음 작업자에게: Task 4(왕복)는 `_post_search`/`_itinerary_ok`/`_fares` 재사용. 부분 완료 스트림은 status ok + error `"partners 3/20"`.

## 2026-09-30 — Claude Code — M2 Task 4: Naver provider (왕복)
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(m2): naver provider roundtrip`
- 한 일: `naver.py`에 `search_roundtrip`(RT body, `itineraryIds` "가는편-오는편" 분리, 양쪽 `_itinerary_ok`, 조건부 가격은 `_fares` 재사용) 추가. 같은 가는편을 공유하는 조합은 dedupe하지 않고 total_price 오름차순 정렬. 테스트 3개 추가.
- 검증: `pytest tests/ -q` 통과, `python -m ruff check .` 통과.
- 다음 작업자에게: Task 5(병합)에서 RtQuote는 `out_flight_key` 중복 가능함에 유의.

## 2026-09-30 — Claude Code — M2 Task 5: 병합 (편명 보조 매칭 + 조건부 최저가)
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(m2): flight-number secondary matching and conditional best price`
- 한 일: `domain/results.py` — `_group`(flight_key 1차 + (date, 공항, 편명) 2차 union-find, 편명 빈 견적 제외), 대표 leg=GF 최저(없으면 전체 최저), 제공자별 최저 1건으로 `prices`, `CondPrice`/`MergedLeg.best_cond`/`ProviderPrice.cond_*` 추가(신선 가격 중 cond 최저 < best_price일 때만). 테스트 5개 추가.
- 검증: `pytest tests/ -q` 174 passed, `python -m ruff check .` 통과.
- 다음 작업자에게: 대표 leg의 flight_key가 GF 키이므로 tracking 키는 GF 기준으로 안정. 표시 계층(Task 6+)에서 `best_cond` 사용.

## 2026-09-30 — Claude Code — M2 Task 6: 왕복 참고가 조건부·제공자 + API 뷰
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(m2): roundtrip reference per provider and conditional fields in API`
- 한 일: `RtReference`에 `rt_provider`/`cond_rt_min`/`cond_label` 추가(rt_min 낸 제공자, 동가면 이름 오름차순 첫째; cond는 신선 스냅샷 중 최저 cond_total_price가 rt_min보다 엄격히 낮을 때만). `api/views.py`에 `best_cond`, `prices[].cond_*`, `rt_reference[].rt_provider/cond_rt_min/cond_label` 추가(기존 키 유지). 테스트 4개 추가·test_trip_view_shape 키 갱신.
- 검증: `pytest tests/ -q` 178 passed, `python -m ruff check .` 통과.
- 다음 작업자에게: 프론트엔드가 새 키를 아직 사용하지 않음.

## 2026-09-30 — Claude Code — M2 Task 7: worker 다중 제공자 실행 + 제공자별 운영 알림
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(m2): run google flights and naver together, per-provider ops alerts`
- 한 일: `worker.py` — `ProviderSpec`, `execute_run/run_with_timeout(providers)`(제공자 호출 예외는 error 스냅샷으로 변환, run은 done), `main_loop`에 `httpx.AsyncClient` 추가·매 run마다 GF/Naver spec 구성, `evaluate_ops`를 제공자별(`ops:{name}` 쿨다운)·`list[str]` 반환으로 변경, 알림에 "카드 조건 시 N원 (라벨 등)" 추가. 테스트 갱신·추가.
- 검증: `pytest tests/ -q` 181 passed, `python -m ruff check .` 통과, `import flight_friend.worker` 성공.
- 다음 작업자에게: 기존 `ops` 알림 kind는 더 이상 쓰이지 않음(`ops:google_flights`로 대체 — 배포 직후 쿨다운이 새로 시작됨).

## 2026-09-30 — Claude Code — M2 Task 7 수정: 타임아웃 시 끝난 제공자 결과 보존
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `fix(m2): keep finished provider results when a run times out`
- 한 일: 제공자 호출을 개별 태스크로 실행, RUN_TIMEOUT 시 끝난 결과는 저장하고 미완료 호출은 취소 후 `error/"timeout"` 스냅샷으로 저장, run은 error·`run_with_timeout`은 True 유지. 호출 팩토리를 `_guarded` 내부에서 호출, main_loop finally에서 crawler/client close 독립 처리.
- 검증: `pytest tests/ -q` 182 passed, ruff 통과.

## 2026-09-30 — Claude Code — M2 Task 8: 화면 조건부 가격 표시, 상세 기본 펼침
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `feat(m2-web): conditional prices, naver seller links, details open by default`
- 한 일: `types.ts`에 `CondPriceView`·`best_cond`·`cond_*`·`rt_provider/cond_rt_min/cond_label` 추가. `LegCard` 상세 기본 펼침 + 큰 토글(`상세 ▴/▾`), 가격 아래 `카드 조건 시 N원`, naver 링크 `판매사 선택 ↗`, 들여쓴 조건 줄. `SelectionBar` 카드 조건 합계 줄 + 왕복 참고에 제공자/조건가. (`providers.ts`는 이미 `naver` 표시명 있어 변경 없음)
- 검증(브라우저 확인, 헤드리스 Chromium 1200px/390px, 로컬 API + GF·Naver 시드): 상세 기본 펼침, 토글 높이 32px, 조건부 줄, GF `예약 ↗`/Naver `판매사 선택 ↗`/들여쓴 조건 행 링크, 선택 바 합계 줄(160,000원)과 왕복 참고(Naver · 카드 조건 시 300,000원), 두 폭 모두 가로 스크롤 없음. 조건 없는 편(B)은 조건 줄 없음.
- 검증(명령): `npm run build` 통과, `pytest tests/ -q` 182 passed, ruff 통과. 시드 데이터는 V2 테이블 truncate로 정리.
- 코드로만 확인(브라우저 미확인): `best_cond`가 best_price보다 비싼 경우 `min()` 처리, `cond_booking_url`이 null일 때 링크 생략, 한 편만 조건부일 때의 합계.
- 다음 작업자에게: 선택 바 왕복 참고 문구에 기존 "편도 합보다 …" 설명을 유지했다(브리프 문구에 덧붙임).

## 2026-09-30 — Claude Code — M2 최종 리뷰 수정 wave
- 브랜치 / 커밋: claude/dazzling-shannon-4x04v7 / fix(m2): alert links follow the cheapest provider; naver deadlines, mixed-airline RT, malformed itineraries
- 한 일: 알림 예약 링크를 최저가 제공자(best_provider의 fresh 항목) 링크로 변경. Naver `_post_search`에 asyncio.wait_for 전체 상한 추가(timeout → error "timeout"). `run_with_timeout` 반환값을 "google_flights 호출 시간 초과"로 한정해 Naver만 멈춘 경우 크롤러를 재생성하지 않음(run은 여전히 error). Naver 왕복 조합에서 가는편/오는편 첫 구간 항공사가 다르면 제외. 필수 필드가 없는 itinerary는 후보만 건너뜀. 테스트 추가(전이적 브릿지, 전부 Naver 대표 견적, 중복 flight_key 최저가, A01 없는 후보 제외 등).
- 검증: `python -m pytest tests/ -q -W error::RuntimeWarning` 192 passed, ruff, import, npm build.
- 결정 / 발견: 배포 직후 Naver의 낮은 A01 가격 때문에 Trip당 "추적 시작 이후 최저" 알림이 한 번 갈 수 있음(TODOS.md 배포 메모).
- 다음 작업자에게: 없음.

## 2026-09-30 — Claude Code — M2 Task 1: OCI 게이트 (사용자 결정으로 사후 확인으로 전환)
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `docs(m2): close OCI gate as post-deploy check`
- 한 일: 사용자 결정 — "이전 V1에서도 잘 됐으니 된다고 가정". 사전 확인(spike 스크립트 실행) 없이 게이트를 닫고, 확인을 배포 후 관측으로 옮김.
- 검증: 없음 (가정). 세션(미국 IP)에서는 새 provider로 실제 API 호출 성공 (ICN→FUK 74편).
- 다음 작업자에게: 배포 후 `/admin`에서 Naver 스냅샷이 `ok`인지 확인. `blocked`/`error`가 3회 이어지면 `ops:naver` 알림이 오고, 그때 브라우저 재시도(설계 D7)를 진행한다. 참고로 V1 Naver 수집은 2026-08-31부터 OCI에서 0건이었다(당시 원인 후보: 헤드리스 기본 UA — 새 provider는 데스크톱 UA로 직접 API 호출).

## 2026-09-30 — Claude Code — M2 배포 확인
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` (master `6d579f5`에서 재시작) / `docs: M2 deployed, next-work order`
- 한 일: 사용자가 배포 후 `/admin`에서 GF·Naver 6개 스냅샷 모두 ✓ 확인(CTS #2, OIT #4 수동 run). TODOS에서 OCI 확인·배포 메모 제거, 진행 순서 기록.
- 다음 작업자에게: FE 대개편 brainstorming부터.

## 2026-09-30 — Claude Code — FE 대개편 설계 (brainstorming)
- 브랜치 / 커밋: `claude/dazzling-shannon-4x04v7` / `docs: FE redesign design`
- 한 일: 결정 — 전면 재설계(시각 > 정보 구조 > 모바일), shadcn/ui + 21st.dev·Mobbin 슬롯 교체, 제공자 배지 + 나란히 비교, Trip 상세 결정 우선 + 데스크톱 2단, 자잘한 변경 11개 전부, 메인 대시보드 카드 + 전체 다시 확인, 제자리 교체 + Vite 6·Tailwind v4, 모던 뉴트럴 테마(zinc+sky, Pretendard). 백엔드는 키 추가만(목록 API 필드, `POST /api/trips/refresh`, 조회 단위 스냅샷 저장·run 진행, next_auto_at, admin error).
- 다음 작업자에게: 사용자 설계 검토 후 writing-plans.
- FE 구현 계획 작성: 9 tasks (1–2 백엔드 API → 3 도구·shadcn·시드/스냅샷 스크립트 → 4 공용 컴포넌트·골격 → 5 대시보드 → 6 새 Trip → 7·8 Trip 상세 → 9 admin·정리).
