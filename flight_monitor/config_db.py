# flight_monitor/config_db.py
import json
import sys

from .storage import get_conn


_ALL_KEYS = ("search_config", "japan_airports", "tfs_templates")


def apply_db_config():
    """main.py 시작 시 1회 호출. SEARCH_CONFIG / JAPAN_AIRPORTS / TFS_TEMPLATES를 DB값으로 in-place 패치."""
    config_mod = sys.modules.get("flight_monitor.config")
    if not config_mod:
        return
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT key, value FROM app_config WHERE key IN {_ALL_KEYS}")
            for key, value in cur.fetchall():
                if key == "search_config":
                    config_mod.SEARCH_CONFIG.update(value)
                elif key == "japan_airports":
                    config_mod.JAPAN_AIRPORTS.clear()
                    config_mod.JAPAN_AIRPORTS.update(value)
                elif key == "tfs_templates":
                    config_mod.TFS_TEMPLATES.clear()
                    config_mod.TFS_TEMPLATES.update(value)
    except Exception as e:
        print(f"[config_db] DB 읽기 실패, 기본값 사용: {e}")


def read_config() -> tuple[dict, dict, dict]:
    config_mod = sys.modules.get("flight_monitor.config")
    try:
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT key, value FROM app_config WHERE key IN {_ALL_KEYS}")
            rows = {k: v for k, v in cur.fetchall()}
    except Exception:
        rows = {}
    sc  = rows.get("search_config")  or (config_mod.SEARCH_CONFIG.copy()  if config_mod else {})
    ja  = rows.get("japan_airports") or (config_mod.JAPAN_AIRPORTS.copy() if config_mod else {})
    tfs = rows.get("tfs_templates")  or (config_mod.TFS_TEMPLATES.copy()  if config_mod else {})
    return sc, ja, tfs


def write_config(search_config: dict, japan_airports: dict, tfs_templates: dict):
    with get_conn() as conn:
        cur = conn.cursor()
        for key, value in [
            ("search_config",  search_config),
            ("japan_airports", japan_airports),
            ("tfs_templates",  tfs_templates),
        ]:
            cur.execute(
                """
                INSERT INTO app_config (key, value) VALUES (%s, %s::jsonb)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, json.dumps(value)),
            )
