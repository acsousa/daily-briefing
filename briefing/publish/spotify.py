"""Publish to Spotify via the save-to-spotify CLI, keeping the show under its episode cap.

Spotify hosts at most 60 episodes per show; past that, creating one fails with
`API error (429)` "You've reached the episode limit. Delete existing episodes to create new
ones." So before each upload we delete the oldest episodes until the show will hold at most
`spotify.max_episodes` (default 55) once the new one lands — a 5-episode buffer under the
hard limit. If the upload still hits the episode-limit 429 (e.g. pruning couldn't run), we
free one slot and retry once.

Safety rails — this code deletes published episodes, so it is deliberately conservative:
- Only the episode-limit 429 triggers a delete. A rate-limit 429 (same status code) never does.
- Oldest-first by `created_at`; if any episode lacks a timestamp we don't prune at all.
- At most MAX_DELETES_PER_RUN deletions per run, so a bad count or config can't wipe the show.
- Pruning trouble is logged loudly but never blocks the day's upload.
"""
from __future__ import annotations

import json
import subprocess
import sys

DEFAULT_MAX_EPISODES = 55
SPOTIFY_HARD_LIMIT = 60
MAX_DELETES_PER_RUN = 10


class PublishError(Exception):
    """A save-to-spotify call failed; the message is the CLI's error text."""


def log(msg: str) -> None:
    # stderr: the daily log captures it, while stdout stays clean for the result JSON
    print(msg, file=sys.stderr, flush=True)


def cli_runner(sts: str):
    """Return run(args) -> dict that calls the CLI in --json mode and raises on any error.

    The CLI reports failures as exit 1 with `{"error": "API error (NNN): ..."}` on stdout.
    """
    def run(args: list[str]) -> dict:
        timeout = 1800 if args[:1] == ["upload"] else 120
        p = subprocess.run([sts, "--json", *args], capture_output=True, text=True, timeout=timeout)
        out = p.stdout.strip()
        try:
            data = json.loads(out) if out else {}
        except json.JSONDecodeError:
            raise PublishError(f"unparseable CLI output (exit {p.returncode}): "
                               f"{out[:300]} {p.stderr.strip()[:300]}")
        if isinstance(data, dict) and data.get("error"):
            raise PublishError(str(data["error"]))
        if p.returncode != 0:
            raise PublishError(f"exit {p.returncode}: {p.stderr.strip()[:300] or out[:300]}")
        return data
    return run


def is_episode_limit(message: str) -> bool:
    """True only for the show-full 429, not the rate-limit 429 that shares its status code."""
    return "429" in message and "episode limit" in message.lower()


def max_episodes(config: dict) -> int:
    """spotify.max_episodes from config, validated to 1..60; falls back to the default."""
    raw = (config.get("spotify") or {}).get("max_episodes", DEFAULT_MAX_EPISODES)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 0
    if not 1 <= n <= SPOTIFY_HARD_LIMIT:
        log(f"!! spotify.max_episodes={raw!r} is invalid (need 1-{SPOTIFY_HARD_LIMIT}); "
            f"using {DEFAULT_MAX_EPISODES}")
        return DEFAULT_MAX_EPISODES
    return n


def list_episodes(run, show_id: str) -> list[dict]:
    """The show's episodes, oldest first. Raises PublishError if the age order is unknowable."""
    eps = run(["episodes", "--show-id", show_id]).get("episodes")
    if not isinstance(eps, list):
        raise PublishError("episode list missing from CLI output")
    if any(not e.get("created_at") or not e.get("episode_uri") for e in eps):
        raise PublishError("episode without created_at/episode_uri — can't tell which is oldest")
    return sorted(eps, key=lambda e: e["created_at"])


def _delete(run, ep: dict) -> None:
    ep_id = ep["episode_uri"].rsplit(":", 1)[-1]
    run(["episodes", "delete", ep_id])
    log(f"   deleted {ep_id}  {ep['created_at']}  {ep.get('title', '')}")


def prune(run, show_id: str, limit: int, dry_run: bool = False) -> list[dict]:
    """Delete the oldest episodes so the show holds at most limit-1, leaving room for one upload.

    Returns the episodes deleted (or, with dry_run, the ones that would be).
    """
    eps = list_episodes(run, show_id)
    target = limit - 1
    excess = len(eps) - target
    log(f">> Episode cap: {len(eps)} on show, limit {limit} — "
        + (f"deleting {excess} oldest" if excess > 0 else "no pruning needed"))
    if excess <= 0:
        return []
    if excess > MAX_DELETES_PER_RUN:
        log(f"!! {excess} over the cap; deleting only {MAX_DELETES_PER_RUN} this run (safety limit)")
        excess = MAX_DELETES_PER_RUN
    victims = eps[:excess]
    if dry_run:
        for ep in victims:
            log(f"   would delete {ep['episode_uri']}  {ep['created_at']}  {ep.get('title', '')}")
        return victims
    deleted = []
    for ep in victims:
        try:
            _delete(run, ep)
            deleted.append(ep)
        except PublishError as exc:
            log(f"!! could not delete {ep['episode_uri']}: {exc}")
    return deleted


def upload(run, mp3: str, title: str, summary: str, show_id: str) -> dict:
    """Upload; on the episode-limit 429, free one slot (oldest) and retry exactly once."""
    args = ["upload", mp3, "--title", title, "--summary", summary, "--show-id", show_id]
    try:
        return run(args)
    except PublishError as exc:
        if not is_episode_limit(str(exc)):
            raise
        log(f"!! upload refused — show is full: {exc}")
    eps = list_episodes(run, show_id)
    if not eps:
        raise PublishError("show reported full but lists no episodes to delete")
    _delete(run, eps[0])
    log(">> retrying upload once")
    return run(args)


def publish(run, mp3: str, title: str, summary: str, show_id: str, limit: int) -> dict:
    """Prune to the cap, then upload. Pruning failures never block the upload."""
    try:
        prune(run, show_id, limit)
    except PublishError as exc:
        log(f"!! episode-cap pruning skipped: {exc} — attempting upload anyway")
    return upload(run, mp3, title, summary, show_id)
