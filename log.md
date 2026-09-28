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
- 다음 task: Task 2
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
- 다음 작업자에게: Task 2로 진행. `flight_friend/db.py`의 `init_schema()`는 append-only 스키마 전제이므로 이후 task에서 UPDATE 로직을 넣지 말 것(스펙 §9.3).
