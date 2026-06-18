"""`brief` CLI. Currently: `brief ingest`."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from .config import load_config, load_profile
from .ingest import FeedAdapter, dedupe, filter_relevant
from .store import Store

DEFAULT_DB = "briefing.db"


def cmd_ingest(args) -> None:
    config = load_config()
    profile = load_profile()
    window = config.get("ingest", {}).get("window_hours", 24)
    since = datetime.now(timezone.utc) - timedelta(hours=window)

    fetched = []
    for src in config.get("sources", []):
        if src.get("type") not in ("rss", "json"):
            continue
        adapter = FeedAdapter(src)
        try:
            articles = adapter.fetch(since)
        except Exception as exc:                      # network/parse failure is per-source
            print(f"  ! {src['id']}: {exc}")
            continue
        print(f"  {src['id']}: {len(articles)}")
        fetched.extend(articles)

    deduped = dedupe(fetched)
    relevant = filter_relevant(deduped, profile)

    store = Store(args.db)
    store.save_many(relevant)
    store.close()
    print(f"fetched {len(fetched)} | deduped {len(deduped)} | relevant {len(relevant)} -> {args.db}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="brief")
    sub = parser.add_subparsers(dest="cmd", required=True)
    ingest = sub.add_parser("ingest", help="fetch, filter to your profile, and store articles")
    ingest.add_argument("--db", default=DEFAULT_DB, help="SQLite path (default: briefing.db)")
    ingest.set_defaults(func=cmd_ingest)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
