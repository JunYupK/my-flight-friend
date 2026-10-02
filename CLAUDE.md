# CLAUDE.md

> **프로젝트 명세 / 아키텍처 / 인터페이스 / 금지사항은 [`AGENTS.md`](./AGENTS.md) 로 이전됨.**
> 본 파일은 LLM 행동 규범과 프로젝트 요약만 담는다. 충돌 시 AGENTS.md 우선.

---

## Behavioral guidelines

Behavioral guidelines to reduce common LLM coding mistakes. **Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- Ask only about decisions that are the user's to make (scope, product behavior, irreversible or outward-facing actions). Otherwise name what's unclear, state the assumption you're taking, and proceed.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## Project: my-flight-friend

ICN 출발 해외 항공권 추적 서비스(V2). 사용자가 만든 Trip(목적지·날짜·선호)마다 Google Flights·Naver 가격을 스냅샷으로 쌓아 최저 조합과 가격 추이를 보여주고, 새 최저가·목표가 도달 시 알림을 보낸다.

상세 명세(레이어, 인터페이스, DB 규칙, 환경변수, 명령어 등)는 `AGENTS.md` 참고.

포트폴리오 서술은 [`docs/PORTFOLIO.md`](./docs/PORTFOLIO.md), 작업 로그·보류 항목·이슈는 `docs/log.md`·`docs/TODOS.md`·`docs/ISSUES.md`.
