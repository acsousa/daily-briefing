"""Scheduled run time = drop_time - lead_hours, wrapping past midnight."""
from briefing.schedule import compute_run_time


def test_basic_subtraction():
    assert compute_run_time("08:00", 2) == (6, 0)
    assert compute_run_time("06:30", 2) == (4, 30)
    assert compute_run_time("12:00", 3) == (9, 0)


def test_wraps_past_midnight():
    assert compute_run_time("01:00", 2) == (23, 0)
    assert compute_run_time("00:15", 1) == (23, 15)
