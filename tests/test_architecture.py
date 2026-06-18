# tests/test_architecture.py
#
# AGENTS.md §2(의존성 방향) / §8(금지사항)을 기계적으로 강제한다.
# 정적 분석(ast)만 사용하므로 DB·크롤러·네트워크 없이 단독 실행된다 —
# 따라서 CI에서 PostgreSQL 서비스 컨테이너 없이도 항상 돌고, 레이어 경계를
# 깨는 import 가 머지되면 즉시 빌드를 깬다.

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# 레이어별 파일 경로 (AGENTS.md §2 표 기준)
STORAGE = ROOT / "flight_monitor" / "storage.py"
ROUTER = ROOT / "flight_front" / "api" / "main.py"
COLLECTORS = sorted((ROOT / "flight_monitor").glob("collector_*.py"))
SERVICES = [
    ROOT / "flight_front" / "api" / "deals_cache.py",
    ROOT / "flight_front" / "api" / "run_state.py",
    ROOT / "flight_front" / "api" / "search_service.py",
    ROOT / "mcp_server.py",
]


def _imported_modules(path: pathlib.Path) -> set[str]:
    """파일이 import 하는 절대 모듈 경로 집합."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
    return mods


def _imports_matching(mods: set[str], *prefixes: str) -> set[str]:
    """주어진 prefix(자기 자신 또는 하위 패키지)에 걸리는 import 만 추려낸다."""
    return {
        m
        for m in mods
        for p in prefixes
        if m == p or m.startswith(p + ".")
    }


# ---------------------------------------------------------------------------
# §8 금지: Repository / Collector 가 웹 프레임워크에 의존하면 안 된다
# ---------------------------------------------------------------------------

def test_storage_does_not_import_fastapi():
    """storage.py(Repository) 는 FastAPI/HTTPException 을 모른다. (AGENTS §8)"""
    bad = _imports_matching(_imported_modules(STORAGE), "fastapi", "starlette")
    assert not bad, f"storage.py 가 웹 프레임워크를 import 함: {bad}"


def test_collectors_do_not_import_fastapi():
    """collector_*.py 는 FastAPI 를 import 하지 않는다. (AGENTS §8)"""
    offenders = {}
    for path in COLLECTORS:
        bad = _imports_matching(_imported_modules(path), "fastapi", "starlette")
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"collector 가 웹 프레임워크를 import 함: {offenders}"


# ---------------------------------------------------------------------------
# §2 의존성 방향: 역방향 / 금지 경로 import 차단
# ---------------------------------------------------------------------------

def test_storage_is_lowest_layer():
    """Repository 는 Collector/Service/Router 를 import 하지 않는다. (AGENTS §2)"""
    mods = _imported_modules(STORAGE)
    bad = _imports_matching(mods, "flight_front", "mcp_server")
    bad |= {m for m in mods if m.startswith("flight_monitor.collector_")}
    assert not bad, f"storage.py 가 상위 레이어를 import 함: {bad}"


def test_router_does_not_import_collectors():
    """Router 는 크롤러를 직접 호출하지 않는다 (router → collector 금지). (AGENTS §2)"""
    mods = _imported_modules(ROUTER)
    bad = {m for m in mods if m.startswith("flight_monitor.collector_")}
    assert not bad, f"api/main.py 가 collector 를 직접 import 함: {bad}"


def test_services_do_not_import_router():
    """Service 는 Router(api/main.py) 를 import 하지 않는다 (역방향 금지). (AGENTS §2)"""
    offenders = {}
    for path in SERVICES:
        if not path.exists():
            continue
        bad = _imports_matching(_imported_modules(path), "flight_front.api.main")
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"Service 가 Router 를 import 함(역방향): {offenders}"


# ---------------------------------------------------------------------------
# §8 + §11: api/main.py 의 직접 SQL(get_conn) 사용은 "동결 후 축소"만 허용
# ---------------------------------------------------------------------------
#
# AGENTS §8 은 "api/main.py 에 SQL 직접 작성"을 금지하지만, §11(Known Issues)에
# 따라 아직 마이그레이션되지 않은 엔드포인트가 남아 있다. 아래 allowlist 는 그
# "남은 빚" 목록이다. 규칙:
#   - 목록에 없는 함수가 get_conn() 을 직접 호출하면 테스트 실패 → 새 위반 차단.
#   - 함수를 storage 계층으로 옮겨 get_conn() 호출이 사라지면, allowlist 에서도
#     반드시 제거해야 한다(test_no_stale_allowlist 가 강제) → 한 방향으로만 풀림.
_GET_CONN_ALLOWLIST = frozenset(
    {
        "upsert_airport",        # POST   /api/airports
        "delete_airport",        # DELETE /api/airports/{code}
        "get_monitor_coverage",  # GET    /api/monitor/coverage
        "get_calendar_prices",   # GET    /api/calendar-prices   (AGENTS §11)
        "get_price_history",      # GET    /api/price-history    (AGENTS §11)
    }
)


def _functions_calling_get_conn(path: pathlib.Path) -> set[str]:
    """get_conn() 을 직접 호출하는, 가장 안쪽으로 감싸는 함수 이름들."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    funcs = [
        (n.name, n.lineno, n.end_lineno)
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    callers: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "get_conn"
        ):
            enclosing = min(
                (f for f in funcs if f[1] <= node.lineno <= f[2]),
                key=lambda f: f[2] - f[1],
                default=None,
            )
            callers.add(enclosing[0] if enclosing else "<module>")
    return callers


def test_no_new_direct_sql_in_router():
    """허용 목록 밖의 새 엔드포인트는 get_conn() 직접 호출 금지. (AGENTS §8/§11)"""
    new_offenders = _functions_calling_get_conn(ROUTER) - _GET_CONN_ALLOWLIST
    assert not new_offenders, (
        "api/main.py 에 새 직접-SQL 엔드포인트가 추가됨: "
        f"{sorted(new_offenders)}. storage.py 로 쿼리를 옮기거나, 정당한 사유가 "
        "있다면 _GET_CONN_ALLOWLIST 에 명시적으로 추가하라."
    )


def test_no_stale_allowlist():
    """이미 마이그레이션된 함수는 allowlist 에서 제거돼야 한다 (래칫 보장)."""
    stale = _GET_CONN_ALLOWLIST - _functions_calling_get_conn(ROUTER)
    assert not stale, (
        f"_GET_CONN_ALLOWLIST 에 더 이상 get_conn() 을 호출하지 않는 항목이 남음: "
        f"{sorted(stale)}. 마이그레이션이 끝났으니 목록에서 삭제하라."
    )
