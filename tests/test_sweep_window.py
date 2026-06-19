# tests/test_sweep_window.py
#
# compute_sweep_window() 순수 단위 테스트 (DB·crawl4ai 불필요).
# sweep을 cron tick에 분산하는 로직의 경계조건을 검증한다.

import calendar
from datetime import date, datetime, timedelta

from flight_monitor.crawler_utils import compute_sweep_window

TODAY = date(2026, 6, 19)
MAX_STAY = 5
RANGE = 12
TICK = 3  # → num_slices = 4


def _at(hour: int) -> datetime:
    return datetime(2026, 6, 19, hour, 0, 0)


def test_slicing_disabled_returns_full_range():
    """tick_months >= range_months면 비활성 → 오늘부터 전체 12개월(+max_stay)."""
    start, end = compute_sweep_window(TODAY, _at(0), RANGE, RANGE, MAX_STAY)
    assert start == TODAY
    # 출발월 12개(2026-06 ~ 2027-05). 마지막 달(2027-05) 말일 31 + max_stay 5 → 2027-06-05
    assert end == date(2027, 6, 5)


def test_tick0_is_near_future():
    """tick 0(자정/정오)은 근미래 슬라이스 — 시작이 오늘."""
    start, end = compute_sweep_window(TODAY, _at(0), RANGE, TICK, MAX_STAY)
    assert start == TODAY
    # 슬라이스: 6,7,8월 → 끝은 8월 말일 + max_stay = 9월 초
    assert end.year == 2026 and end.month == 9


def test_tick_index_advances_by_3h_block():
    """3시간 tick마다 다음 슬라이스로 이동."""
    # tick 1 (03:00) → 9,10,11월
    start, _ = compute_sweep_window(TODAY, _at(3), RANGE, TICK, MAX_STAY)
    assert start == date(2026, 9, 1)
    # tick 2 (06:00) → 12,1,2월
    start, _ = compute_sweep_window(TODAY, _at(6), RANGE, TICK, MAX_STAY)
    assert start == date(2026, 12, 1)
    # tick 3 (09:00) → 3,4,5월(2027)
    start, _ = compute_sweep_window(TODAY, _at(9), RANGE, TICK, MAX_STAY)
    assert start == date(2027, 3, 1)


def test_round_robin_wraps():
    """num_slices=4 → 12:00은 다시 tick 0(근미래)."""
    s0, e0 = compute_sweep_window(TODAY, _at(0), RANGE, TICK, MAX_STAY)
    s12, e12 = compute_sweep_window(TODAY, _at(12), RANGE, TICK, MAX_STAY)
    assert (s0, e0) == (s12, e12)


def test_start_never_before_today():
    """근미래 슬라이스라도 과거 날짜는 수집하지 않는다."""
    # 6월 19일이라 슬라이스 시작(6월 1일)이 today보다 앞 → today로 클램프
    start, _ = compute_sweep_window(TODAY, _at(0), RANGE, TICK, MAX_STAY)
    assert start == TODAY
    assert start >= TODAY


def test_end_includes_max_stay_extension():
    """end_date는 마지막 출발월 말일 + max_stay(복귀편 포함)."""
    _, end = compute_sweep_window(TODAY, _at(3), RANGE, TICK, MAX_STAY)
    # tick 1 마지막 달 = 11월, 말일 30일 + 5 = 12월 5일
    _, last = calendar.monthrange(2026, 11)
    assert end == date(2026, 11, last) + timedelta(days=MAX_STAY)


def test_all_ticks_cover_full_range():
    """하루 8개 tick의 슬라이스 합집합이 range_months 전체를 덮는다(공백 없음)."""
    covered_months: set[tuple[int, int]] = set()
    for hour in range(0, 24, 3):
        start, end = compute_sweep_window(TODAY, _at(hour), RANGE, TICK, MAX_STAY)
        d = date(start.year, start.month, 1)
        while d <= end:
            covered_months.add((d.year, d.month))
            # 다음 달
            d = date(d.year + d.month // 12, d.month % 12 + 1, 1)
    # 6월(2026)부터 12개 출발월이 모두 포함되어야 함
    expect = set()
    y, m = 2026, 6
    for _ in range(RANGE):
        expect.add((y, m))
        y, m = (y + m // 12, m % 12 + 1)
    assert expect <= covered_months


def test_indivisible_range_clamps_last_slice():
    """range가 tick으로 안 나눠떨어져도 마지막 슬라이스가 범위를 넘지 않는다."""
    # range=10, tick=3 → slices: [0-2],[3-5],[6-8],[9] (마지막 1개월)
    start, end = compute_sweep_window(TODAY, _at(9), 10, 3, MAX_STAY)
    # tick 3 → 시작월 9개월 뒤 = 2027-03, 길이 min(3, 10-9)=1 → 출발월은 3월만.
    # end는 복귀편 위해 3월 말일 + max_stay = 2027-04-05.
    assert start == date(2027, 3, 1)
    assert end == date(2027, 3, 31) + timedelta(days=MAX_STAY)
