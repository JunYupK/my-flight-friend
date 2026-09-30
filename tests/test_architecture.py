# tests/test_architecture.py
#
# AGENTS.md §2(의존성 방향) / §8(금지사항)을 기계적으로 강제한다.
# 정적 분석(ast)만 사용하므로 DB·크롤러·네트워크 없이 단독 실행된다 —
# 따라서 CI에서 PostgreSQL 서비스 컨테이너 없이도 항상 돌고, 레이어 경계를
# 깨는 import 가 머지되면 즉시 빌드를 깬다.

import ast
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _module_name(path: pathlib.Path) -> str:
    """파일 경로를 절대 모듈 경로로 변환 (flight_friend/api/main.py → flight_friend.api.main)."""
    rel = path.resolve().relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def _imported_modules(path: pathlib.Path) -> set[str]:
    """파일이 import 하는 모듈/심볼의 절대 경로 집합.

    `from pkg import name` 은 `pkg` 뿐 아니라 `pkg.name` 도 포함시킨다 — 그래야
    `from flight_friend import providers` 같은 레이어 위반을 잡을 수 있다.
    상대 import(`from . import main`)는 파일 위치 기준으로 절대 경로로 해석한다.
    """
    pkg_parts = _module_name(path).split(".")[:-1]  # 이 모듈을 담은 패키지
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                # 상대 import: 패키지에서 (level-1) 단계 위로 올라간 경로가 기준
                anchor = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                base = ".".join(anchor)
                if node.module:
                    base = f"{base}.{node.module}" if base else node.module
            if base:
                mods.add(base)
            for alias in node.names:
                mods.add(f"{base}.{alias.name}" if base else alias.name)
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
# flight_friend/* 레이어 규칙 — AGENTS.md §2 / §8
# ---------------------------------------------------------------------------

V2 = ROOT / "flight_friend"
V2_VIEWS = V2 / "api" / "views.py"
V2_API_MAIN = V2 / "api" / "main.py"
V2_DOMAIN = sorted((V2 / "domain").glob("*.py"))
V2_PROVIDERS = sorted((V2 / "providers").glob("*.py"))
V2_DATA = [V2 / "db.py", V2 / "repo.py"]


def test_v2_files_exist():
    """규칙 대상이 사라져 아래 테스트가 조용히 공회전하지 않게 한다."""
    assert V2_VIEWS.exists() and V2_API_MAIN.exists() and V2_DOMAIN and V2_PROVIDERS
    assert all(p.exists() for p in V2_DATA)


def test_v2_non_api_layers_do_not_import_web_framework():
    """views/domain/providers/db/repo 는 fastapi/starlette 를 모른다."""
    offenders = {}
    for path in [V2_VIEWS, *V2_DOMAIN, *V2_PROVIDERS, *V2_DATA]:
        bad = _imports_matching(_imported_modules(path), "fastapi", "starlette")
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"V2 비-API 레이어가 웹 프레임워크를 import 함: {offenders}"


def test_v2_api_main_does_not_import_providers():
    """api/main.py 는 provider(크롤러)를 직접 호출하지 않는다 — 재확인은 worker 가 수행."""
    bad = _imports_matching(_imported_modules(V2_API_MAIN), "flight_friend.providers")
    assert not bad, f"api/main.py 가 providers 를 import 함: {bad}"


def test_v2_domain_does_not_import_db_or_repo():
    """domain/* 은 순수 로직 — DB 접근(db/repo)을 import 하지 않는다."""
    offenders = {}
    for path in V2_DOMAIN:
        bad = _imports_matching(
            _imported_modules(path), "flight_friend.db", "flight_friend.repo"
        )
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"domain 이 db/repo 를 import 함: {offenders}"
