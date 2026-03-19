# flight_monitor/config_db.py
import json
import sys

from .storage import get_conn


def apply_db_config():
    """main.py 시작 시 1회 호출. SEARCH_CONFIG를 DB값으로, JAPAN_AIRPORTS/TFS_TEMPLATES를 airports 테이블로 패치."""
    config_mod = sys.modules.get("flight_monitor.config")
    if not config_mod:
        return
    try:
        with get_conn() as conn:
            cur = conn.cursor()

            # search_config
            cur.execute("SELECT value FROM app_config WHERE key = 'search_config'")
            row = cur.fetchone()
            if row:
                config_mod.SEARCH_CONFIG.update(row[0])

            # airports 테이블 → JAPAN_AIRPORTS, TFS_TEMPLATES
            cur.execute("SELECT code, name, tfs_out, tfs_in FROM airports")
            rows = cur.fetchall()
            if rows:
                config_mod.JAPAN_AIRPORTS.clear()
                config_mod.TFS_TEMPLATES.clear()
                for code, name, tfs_out, tfs_in in rows:
                    config_mod.JAPAN_AIRPORTS[code] = name
                    if tfs_out:
                        config_mod.TFS_TEMPLATES[f"ICN_{code}"] = tfs_out
                    if tfs_in:
                        config_mod.TFS_TEMPLATES[f"{code}_ICN"] = tfs_in
    except Exception as e:
        print(f"[config_db] DB 읽기 실패, 기본값 사용: {e}")


def read_config() -> dict:
    config_mod = sys.modules.get("flight_monitor.config")
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT value FROM app_config WHERE key = 'search_config'")
            row = cur.fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return config_mod.SEARCH_CONFIG.copy() if config_mod else {}


def write_config(search_config: dict):
    # search_months는 항상 실행 시점 기준으로 동적 생성 — DB에 고정값 저장 방지
    saved = {k: v for k, v in search_config.items() if k != "search_months"}
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO app_config (key, value) VALUES ('search_config', %s::jsonb)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (json.dumps(saved),),
        )
