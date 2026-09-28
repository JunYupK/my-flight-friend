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
- 다음 task: 계획 승인 후 Task 1부터
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
