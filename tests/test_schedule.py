"""Scheduling: run-time math, cron line, and per-OS mechanism dispatch."""
import platform
import shutil

from briefing import schedule
from briefing.schedule import compute_run_time


def test_basic_subtraction():
    assert compute_run_time("08:00", 2) == (6, 0)
    assert compute_run_time("06:30", 2) == (4, 30)
    assert compute_run_time("12:00", 3) == (9, 0)


def test_wraps_past_midnight():
    assert compute_run_time("01:00", 2) == (23, 0)
    assert compute_run_time("00:15", 1) == (23, 15)


def test_cron_line_format():
    line = schedule._cron_line(6, 5)
    assert line.startswith("5 6 * * * ")
    assert str(schedule.RUNNER) in line
    assert schedule.CRON_MARKER in line


def test_mechanism_dispatch(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    assert schedule.mechanism() == "launchd"

    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/systemctl")
    assert schedule.mechanism() == "systemd"
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert schedule.mechanism() == "cron"

    monkeypatch.setattr(platform, "system", lambda: "Windows")
    assert schedule.mechanism() == "unsupported"
