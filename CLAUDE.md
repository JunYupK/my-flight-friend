# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

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

ICN 출발 일본 항공권 최저가 모니터링 도구. 복수 데이터 소스에서 편도 항공편을 수집해 왕복 조합을 만들고, 목표가 이하 딜을 알림으로 전송한다.

### Commands

```bash
# PostgreSQL DB 시작 (필수)
docker compose up -d

# 항공권 수집 실행
python main.py

# 테스트 실행
pytest tests/

# 단일 테스트 클래스/함수
pytest tests/test_flight_monitor.py::TestShouldNotify
pytest tests/test_flight_monitor.py::TestShouldNotify::test_price_drop_triggers_realert
```

### Environment Variables

`DATABASE_URL` is required. Others are optional (gracefully skipped if missing):
```
DATABASE_URL=postgresql://flight_user:flight_pass@localhost:5432/flights
AMADEUS_CLIENT_ID=...
AMADEUS_CLIENT_SECRET=...
CALLMEBOT_PHONE=...
CALLMEBOT_API_KEY=...
GMAIL_ADDRESS=...
GMAIL_APP_PASSWORD=...
ALERT_EMAIL=...
```

### Architecture

**Data flow:** `main.py` → collectors → `storage.save_prices()` → alert check → `notifier.notify()`

**Data sources** (all produce the same offer dict shape):
- `collector_amadeus.py` — Amadeus REST API (FSC carriers KE/OZ only). Requires `AMADEUS_CLIENT_ID`/`AMADEUS_CLIENT_SECRET`.
- `collector_google_flights.py` — crawl4ai headless browser. Scrapes `li.pIav2d` cards via JS injection. Encodes date into base64 `tfs=` URL parameter by replacing bytes in `_TFS_TEMPLATES`. Only ICN↔TYO is registered; other routes need new tfs= values added.
- `collector_lcc.py` — Naver flight GraphQL API (pagination via `galileoFlag`/`travelBizFlag`). Not called from `main.py` currently (only `fetch_fsc_offers` + `fetch_google_flights_offers` are used).

**Offer dict shape** (all collectors must produce these fields):
```python
{
  "source", "trip_type", "origin", "destination", "destination_name",
  "departure_date", "return_date", "stay_nights", "price", "currency",
  "out_airline", "in_airline", "is_mixed_airline", "checked_at",
  # optional: out_dep_time, out_arr_time, out_duration_min, out_stops,
  #           in_dep_time,  in_arr_time,  in_duration_min,  in_stops
}
```

**Storage** (`storage.py`): PostgreSQL via psycopg2. Uses `DATABASE_URL` env var. Tables: `price_history` (raw append-only), `alert_state` (dedup/cooldown). View: `v_best_observed` (min price per route/airline combo).

**Alert logic**: `should_notify()` blocks re-alerts within `alert_cooldown_hours` unless price drops by ≥ `alert_realert_drop_krw`.

**MCP server** (`mcp_server.py`): Three query functions (`get_best_deals`, `get_price_history`, `explain_deal`) for use with Claude Desktop. **Note:** currently uses SQLite-style `?` placeholders and `conn.execute()` — incompatible with the psycopg2 PostgreSQL backend in `storage.py`. Needs porting to `%s` placeholders and `psycopg2.extras.RealDictCursor`.

**Config** (`config.py`): All tunable parameters live in `SEARCH_CONFIG`. Key settings:
- `lcc_max_days`: set to `None` for full-month collection; currently `5` for testing
- `search_months`: list of `"YYYY-MM"` strings
- `target_price_krw`: alert threshold in KRW

### Known Issues (see ISSUES.md for details)

1. `mcp_server.py` uses SQLite API (`?` placeholders) — broken against PostgreSQL
2. Tests in `tests/` monkeypatch `storage.DB_PATH` (SQLite path) which no longer exists in `storage.py` after PostgreSQL migration — tests are currently broken
3. `lcc_max_days` is set to `5` (test mode); change to `None` for production
4. Only ICN↔TYO tfs templates registered in `collector_google_flights.py`
5. Foreign LCC airlines (Peach, Zipair, etc.) missing from `AIRLINES` list in `_extract_js()`
