"""CLI: `python -m briefing.publish upload|prune` — used by make_briefing.sh.

upload  prune to spotify.max_episodes, upload, print the CLI's result JSON on stdout
prune   prune only (use --dry-run to see what would be deleted)
Progress and errors go to stderr; exit 1 on failure.
"""
from __future__ import annotations

import argparse
import json
import sys

from ..config import load_config
from .spotify import PublishError, cli_runner, log, max_episodes, prune, publish


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m briefing.publish")
    ap.add_argument("--sts", required=True, help="path to the save-to-spotify CLI")
    ap.add_argument("--show-id", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    up = sub.add_parser("upload")
    up.add_argument("mp3")
    up.add_argument("--title", required=True)
    up.add_argument("--summary", required=True)
    pr = sub.add_parser("prune")
    pr.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    run = cli_runner(a.sts)
    limit = max_episodes(load_config())
    try:
        if a.cmd == "prune":
            prune(run, a.show_id, limit, dry_run=a.dry_run)
        else:
            print(json.dumps(publish(run, a.mp3, a.title, a.summary, a.show_id, limit)))
    except PublishError as exc:
        log(f"!! {a.cmd} failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
