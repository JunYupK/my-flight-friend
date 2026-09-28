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
- 구현 계획: `docs/superpowers/plans/2026-09-28-flight-friend-v2-m1.md` (M1, 17 tasks — 사용자 검토 대기, 실행 전)
- 다음 task: Task 4
- 진행 중인 외부 작업: OCI 반복 측정(차단 여부) — 결과로 설계 §5.1 갱신 주기·W 확정 예정
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
  - `load_snapshots`/`recent_runs` 모두 legs/rts(또는 snapshots) 조회에 N+1 쿼리를 사용 — snapshot/run 개수가 적은 전제(트립당 관측 주기 수 시간 단위)에서 단순성 우선, 성능 이슈 발생 시 이후 task에서 JOIN 집계로 전환 가능.
- 다음 작업자에게: Task 4로 진행. `snapshots`/`leg_quotes`/`rt_quotes`/`alerts`는 계속 append-only이므로 UPDATE 로직 추가 금지. `recent_runs(limit=3)`의 snapshots 배열(provider/kind/direction/status)은 워커에서 GF 편도 연속 실패 감지에 쓰일 예정이니 필드명 변경 시 주의.
