# tests/v2/conftest.py

import os
import sys

import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from flight_friend import db


@pytest.fixture(autouse=True)
def v2_db():
    """각 테스트마다 V2 테이블을 초기화. init_schema()로 테이블 보장 후 TRUNCATE."""
    db.init_schema()
    yield
    with db.get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            TRUNCATE trips, search_runs, snapshots, leg_quotes, rt_quotes, alerts
            RESTART IDENTITY CASCADE
        """)
