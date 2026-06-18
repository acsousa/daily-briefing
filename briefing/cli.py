"""`brief` CLI: `ingest` and `generate`."""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .cluster import cluster_articles
from .config import load_config, load_profile
from .continuity import match_threads, update_threads
from .editor import edit_rundown
from .ingest import FeedAdapter, dedupe, filter_relevant
from .ingest.extract import fetch_fulltext
from .ingest.weather import get_forecast
from .plan import build_plan
from .rank import rank_clusters
from .script import write_script
from .store import RawArticle, Store, StoryThread

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = str(REPO_ROOT / "briefing.db")
BRIEFINGS_DIR = REPO_ROOT / "briefings"
MAX_FULLTEXT_PER_CLUSTER = 3


def run_ingest(config, profile, store) -> list[RawArticle]:
    window = config.get("ingest", {}).get("window_hours", 24)
    since = datetime.now(timezone.utc) - timedelta(hours=window)
    fetched = []
    for src in config.get("sources", []):
        if src.get("type") not in ("rss", "json"):
            continue
        try:
            articles = FeedAdapter(src).fetch(since)
        except Exception as exc:
            print(f"  ! {src['id']}: {exc}")
            continue
        fetched.extend(articles)
    deduped = dedupe(fetched)
    relevant = filter_relevant(deduped, profile)
    store.save_many(relevant)
    print(f"ingest: fetched {len(fetched)} | deduped {len(deduped)} | relevant {len(relevant)}")
    return relevant


def cmd_ingest(args) -> None:
    store = Store(args.db)
    run_ingest(load_config(), load_profile(), store)
    store.close()
    print(f"-> {args.db}")


def _recent_articles(store, window_hours) -> list[RawArticle]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    return [a for a in store.list(RawArticle)
            if a.published_at.replace(tzinfo=a.published_at.tzinfo or timezone.utc) >= cutoff]


def cmd_generate(args) -> None:
    config = load_config()
    profile = load_profile()
    if args.minutes:
        config.setdefault("episode", {})["target_duration_minutes"] = args.minutes
    today = date.today()
    store = Store(args.db)

    articles = (_recent_articles(store, config.get("ingest", {}).get("window_hours", 24))
                if args.skip_ingest else run_ingest(config, profile, store))
    if not articles:
        raise SystemExit("no relevant articles — run `brief ingest` first or check feeds")

    clusters = cluster_articles(articles)
    articles_by_id = {a.id: a for a in articles}
    clusters_by_id = {c.id: c for c in clusters}

    win = config.get("continuity", {})
    month = win.get("month_days", 30)
    threads = [t for t in store.list(StoryThread)
               if (today - t.last_briefed).days <= month]
    decisions = match_threads(clusters, threads, today, win)
    novelty = {cid: d["novelty"] for cid, d in decisions.items()}

    weights = config.get("ranking", {}).get("weights")
    ranked = rank_clusters(clusters, profile, weights, novelty)

    weather = None
    wcfg = config.get("weather")
    if wcfg and (wcfg.get("latitude") or wcfg.get("longitude")):
        try:
            weather = get_forecast(wcfg["latitude"], wcfg["longitude"])
        except Exception as exc:
            print(f"  ! weather: {exc}")

    plan = build_plan(ranked, profile, config, has_weather=bool(weather),
                      today=today, novelty_by_cluster=novelty)

    headline_ids = [s.story_cluster_id for s in plan.segments if s.kind == "headline"]
    print(f"plan: {len(plan.segments)} segments "
          f"({plan.target_duration_sec // 60} min target), {len(headline_ids)} stories")
    for sid in headline_ids:
        c = clusters_by_id[sid]
        d = decisions.get(sid, {})
        print(f"  - [{d.get('status', 'new'):10}] {c.title[:70]}  (score {c.score:.2f})")

    if args.dry_run:
        store.close()
        print("\n(dry run — no LLM calls, no files written)")
        return

    # full text only for the stories that made the cut
    fulltext_by_id = {}
    for sid in headline_ids:
        for aid in clusters_by_id[sid].article_ids[:MAX_FULLTEXT_PER_CLUSTER]:
            art = articles_by_id.get(aid)
            if art:
                fulltext_by_id[aid] = fetch_fulltext(art.url)

    from .llm import LLM
    llm = LLM(config)
    editor_output = edit_rundown(llm, plan, clusters_by_id, articles_by_id, decisions, profile)
    briefing_text, episode_segments, briefed = write_script(
        llm, plan, editor_output, clusters_by_id, articles_by_id, fulltext_by_id,
        profile, weather, today)

    BRIEFINGS_DIR.mkdir(exist_ok=True)
    (BRIEFINGS_DIR / "briefing.txt").write_text(briefing_text)
    episode = {
        "date": today.isoformat(),
        "through_line": editor_output.through_line,
        "plan": plan.model_dump(mode="json"),
        "segments": [s.model_dump(mode="json") for s in episode_segments],
    }
    (BRIEFINGS_DIR / "episode.json").write_text(json.dumps(episode, indent=2))

    store.save_many(clusters)
    store.save(plan)
    store.save_many(episode_segments)
    update_threads(store, briefed, decisions, today)
    store.close()

    print(f"\nwrote {BRIEFINGS_DIR / 'briefing.txt'} and episode.json")
    print("next: ./make_briefing.sh  (renders + uploads)")


def cmd_config(args) -> None:
    from .web import serve
    serve(port=args.port, open_browser=not args.no_browser)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="brief")
    sub = parser.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="fetch, filter to your profile, and store articles")
    pi.add_argument("--db", default=DEFAULT_DB)
    pi.set_defaults(func=cmd_ingest)

    pg = sub.add_parser("generate", help="ingest -> cluster -> rank -> plan -> edit -> script")
    pg.add_argument("--db", default=DEFAULT_DB)
    pg.add_argument("--skip-ingest", action="store_true", help="reuse stored articles")
    pg.add_argument("--minutes", type=int, default=None, help="override target duration")
    pg.add_argument("--dry-run", action="store_true",
                    help="run through planning only; no LLM calls or files")
    pg.set_defaults(func=cmd_generate)

    pc = sub.add_parser("config", help="open the SIGNAL web UI to edit profile.yaml/config.yaml")
    pc.add_argument("--port", type=int, default=8765)
    pc.add_argument("--no-browser", action="store_true")
    pc.set_defaults(func=cmd_config)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
