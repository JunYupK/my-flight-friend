# tests/conftest.py

import os
import sys

import pytest

# 프로젝트 루트를 sys.path에 추가 (패키지 설치 없이 flight_friend import)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from flight_friend import db


def pytest_configure(config):
    config.addinivalue_line("markers", "no_db: DB 초기화 없이 실행 (정적 분석 테스트)")


@pytest.fixture(autouse=True)
def clean_db(request):
    """각 테스트마다 테이블을 초기화. init_schema()로 테이블 보장 후 TRUNCATE.

    `pytestmark = pytest.mark.no_db` 모듈은 DB 없이 돈다.
    """
    if request.node.get_closest_marker("no_db"):
        yield
        return
    db.init_schema()
    yield
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            TRUNCATE trips, search_runs, snapshots, leg_quotes, rt_quotes, alerts
            RESTART IDENTITY CASCADE
        """)
