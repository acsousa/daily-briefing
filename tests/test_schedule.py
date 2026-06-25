"""Scheduling: run-time math, cron line, and per-OS mechanism dispatch."""
import platform
import shutil
import types

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
    assert f'"{schedule.RUNNER}"' in line          # runner path is quoted (handles spaces)
    assert schedule.CRON_MARKER in line


def test_cron_install_and_uninstall(monkeypatch):
    """install()/uninstall() add then cleanly remove our marked crontab line (cron path)."""
    monkeypatch.setattr(schedule.platform, "system", lambda: "Linux")
    monkeypatch.setattr(schedule.shutil, "which", lambda _: None)        # no systemctl -> cron
    monkeypatch.setattr(schedule, "load_config",
                        lambda: {"schedule": {"drop_time": "08:00", "lead_hours": 2}})
    store = {"tab": "0 9 * * * /some/other/job\n"}                        # a pre-existing entry

    def fake_run(cmd, **kw):
        if cmd[:2] == ["crontab", "-l"]:
            return types.SimpleNamespace(returncode=0, stdout=store["tab"])
        if cmd == ["crontab", "-"]:
            store["tab"] = kw.get("input", "")
        return types.SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(schedule.subprocess, "run", fake_run)

    hour, minute, mech = schedule.install()
    assert mech == "cron" and (hour, minute) == (6, 0)
    assert schedule.CRON_MARKER in store["tab"]
    assert "0 6 * * *" in store["tab"]
    assert "/some/other/job" in store["tab"]                             # didn't clobber other jobs

    schedule.install()                                                   # idempotent — no duplicate
    assert store["tab"].count(schedule.CRON_MARKER) == 1

    assert schedule.uninstall() == "cron"
    assert schedule.CRON_MARKER not in store["tab"]
    assert "/some/other/job" in store["tab"]                             # other jobs survive


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
