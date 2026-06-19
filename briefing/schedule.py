"""macOS launchd scheduling: run the daily briefing `lead_hours` before `drop_time`."""
from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

from .config import REPO_ROOT, load_config

LABEL = "com.signal.dailybriefing"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
RUNNER = REPO_ROOT / "run_daily.sh"


def compute_run_time(drop_time: str, lead_hours: int) -> tuple[int, int]:
    """Return (hour, minute) = drop_time - lead_hours, wrapping past midnight."""
    h, m = (int(x) for x in drop_time.split(":"))
    total = (h * 60 + m - int(lead_hours) * 60) % (24 * 60)
    return total // 60, total % 60


def _schedule_from_config() -> tuple[int, int]:
    sched = load_config().get("schedule") or {}
    return compute_run_time(sched.get("drop_time", "08:00"), sched.get("lead_hours", 2))


def install() -> tuple[int, int]:
    hour, minute = _schedule_from_config()
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        "Label": LABEL,
        "ProgramArguments": ["/bin/bash", str(RUNNER)],
        "WorkingDirectory": str(REPO_ROOT),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "RunAtLoad": False,
        "StandardOutPath": str(REPO_ROOT / "briefings" / "schedule.log"),
        "StandardErrorPath": str(REPO_ROOT / "briefings" / "schedule.log"),
    }
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)],
                   capture_output=True)               # ignore "not loaded"
    subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True, capture_output=True)
    return hour, minute


def uninstall() -> None:
    subprocess.run(["launchctl", "unload", str(PLIST_PATH)], capture_output=True)
    PLIST_PATH.unlink(missing_ok=True)
