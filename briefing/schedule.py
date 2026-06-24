"""Cross-platform daily scheduling: run the briefing `lead_hours` before `drop_time`.

Picks the right mechanism for the OS automatically:
- macOS  -> launchd user agent
- Linux  -> systemd user timer if available, else cron
"""
from __future__ import annotations

import platform
import plistlib
import shutil
import subprocess
from pathlib import Path

from .config import REPO_ROOT, load_config

LABEL = "com.signal.dailybriefing"
RUNNER = REPO_ROOT / "run_daily.sh"
LOG = REPO_ROOT / "briefings" / "schedule.log"

PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
SYSTEMD_DIR = Path.home() / ".config" / "systemd" / "user"
SYSTEMD_UNIT = "signal-daily-briefing"
CRON_MARKER = "# signal-daily-briefing"


def compute_run_time(drop_time: str, lead_hours: int) -> tuple[int, int]:
    """Return (hour, minute) = drop_time - lead_hours, wrapping past midnight."""
    h, m = (int(x) for x in drop_time.split(":"))
    total = (h * 60 + m - int(lead_hours) * 60) % (24 * 60)
    return total // 60, total % 60


def _schedule_from_config() -> tuple[int, int]:
    sched = load_config().get("schedule") or {}
    return compute_run_time(sched.get("drop_time", "08:00"), sched.get("lead_hours", 2))


def mechanism() -> str:
    system = platform.system()
    if system == "Darwin":
        return "launchd"
    if system == "Linux":
        return "systemd" if shutil.which("systemctl") else "cron"
    return "unsupported"


def install() -> tuple[int, int, str]:
    hour, minute = _schedule_from_config()
    m = mechanism()
    {"launchd": _install_launchd, "systemd": _install_systemd, "cron": _install_cron}.get(
        m, _unsupported)(hour, minute)
    return hour, minute, m


def uninstall() -> str:
    m = mechanism()
    {"launchd": _uninstall_launchd, "systemd": _uninstall_systemd,
     "cron": _uninstall_cron}.get(m, lambda: None)()
    return m


def _unsupported(*_):
    raise SystemExit(f"unsupported platform: {platform.system()} — schedule run_daily.sh manually")


# ---- macOS launchd ----------------------------------------------------------
def _install_launchd(hour, minute):
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/bash", str(RUNNER)],
        "WorkingDirectory": str(REPO_ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True, capture_output=True)


def _uninstall_launchd():
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink(missing_ok=True)


# ---- Linux systemd user timer ----------------------------------------------
def _install_systemd(hour, minute):
    SYSTEMD_DIR.mkdir(parents=True, exist_ok=True)
    (SYSTEMD_DIR / f"{SYSTEMD_UNIT}.service").write_text(
        "[Unit]\nDescription=SIGNAL daily briefing\n\n"
        "[Service]\nType=oneshot\n"
        f"WorkingDirectory={REPO_ROOT}\nExecStart=/bin/bash {RUNNER}\n")
    (SYSTEMD_DIR / f"{SYSTEMD_UNIT}.timer").write_text(
        "[Unit]\nDescription=SIGNAL daily briefing timer\n\n"
        f"[Timer]\nOnCalendar=*-*-* {hour:02d}:{minute:02d}:00\nPersistent=true\n\n"
        "[Install]\nWantedBy=timers.target\n")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True, capture_output=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", f"{SYSTEMD_UNIT}.timer"],
                   check=True, capture_output=True)
    subprocess.run(["loginctl", "enable-linger", str(Path.home().name)], capture_output=True)


def _uninstall_systemd():
    subprocess.run(["systemctl", "--user", "disable", "--now", f"{SYSTEMD_UNIT}.timer"],
                   capture_output=True)
    (SYSTEMD_DIR / f"{SYSTEMD_UNIT}.timer").unlink(missing_ok=True)
    (SYSTEMD_DIR / f"{SYSTEMD_UNIT}.service").unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)


# ---- Linux cron -------------------------------------------------------------
def _cron_line(hour, minute) -> str:
    return f"{minute} {hour} * * * {RUNNER} {CRON_MARKER}"


def _read_crontab() -> list[str]:
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else []


def _write_crontab(lines: list[str]):
    body = ("\n".join(lines) + "\n") if lines else ""
    subprocess.run(["crontab", "-"], input=body, text=True, check=True)


def _install_cron(hour, minute):
    lines = [l for l in _read_crontab() if CRON_MARKER not in l]
    lines.append(_cron_line(hour, minute))
    _write_crontab(lines)


def _uninstall_cron():
    _write_crontab([l for l in _read_crontab() if CRON_MARKER not in l])
