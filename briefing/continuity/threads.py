"""Cross-episode continuity: match today's clusters to ongoing story threads.

Don't repeat what was already briefed — recap and build on developing stories, and
down-weight stories briefed recently with nothing new. Looks back across day/week/month
windows (configurable), not just yesterday.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta

from ..store import StoryThread
from ..text import jaccard, tokens

MATCH_THRESHOLD = 0.30


def _match(cluster, threads):
    ctok = tokens(cluster.title)
    best, best_score = None, 0.0
    for t in threads:
        score = jaccard(ctok, tokens(t.title))
        if t.topic in cluster.topics:
            score += 0.1
        if score > best_score:
            best, best_score = t, score
    return best if best_score >= MATCH_THRESHOLD else None


def match_threads(clusters, existing_threads, today: date, windows: dict) -> dict:
    """Return {cluster_id: {status, novelty, recap, thread}}.

    novelty: 1.0 brand-new; lower when the matched thread was briefed recently. A thread
    last briefed within recent_days with no genuinely newer article is heavily damped.
    """
    recent = windows.get("recent_days", 1)
    week = windows.get("week_days", 7)
    month = windows.get("month_days", 30)
    out = {}
    for c in clusters:
        thread = _match(c, existing_threads)
        if thread is None:
            out[c.id] = {"status": "new", "novelty": 1.0, "recap": None, "thread": None}
            continue
        age = (today - thread.last_briefed).days
        has_new = c.last_updated.date() > thread.last_briefed
        if age <= recent:
            novelty = 0.7 if has_new else 0.2     # just covered; only surface real movement
        elif age <= week:
            novelty = 0.85 if has_new else 0.5
        elif age <= month:
            novelty = 0.95
        else:
            novelty = 1.0                          # dormant long enough to feel fresh again
        out[c.id] = {
            "status": "developing",
            "novelty": novelty,
            "recap": thread.summary_so_far or None,
            "thread": thread,
        }
    return out


def update_threads(store, briefed, decisions: dict, today: date) -> list[StoryThread]:
    """Create/update threads for the clusters that made it into the episode.

    `briefed` is a list of (cluster, summary) for segments that were scripted.
    """
    saved = []
    for cluster, summary in briefed:
        d = decisions.get(cluster.id, {})
        thread = d.get("thread")
        if thread is None:
            tid = hashlib.sha256(f"{today}:{cluster.id}".encode()).hexdigest()[:16]
            thread = StoryThread(
                id=tid,
                title=cluster.title,
                topic=cluster.topics[0] if cluster.topics else "general",
                status="new",
                first_briefed=today,
                last_briefed=today,
                article_ids=list(cluster.article_ids),
                cluster_ids=[cluster.id],
                summary_so_far=summary,
                times_briefed=1,
            )
        else:
            thread = thread.model_copy(update={
                "status": "developing",
                "last_briefed": today,
                "article_ids": sorted(set(thread.article_ids) | set(cluster.article_ids)),
                "cluster_ids": sorted(set(thread.cluster_ids) | {cluster.id}),
                "summary_so_far": summary or thread.summary_so_far,
                "times_briefed": thread.times_briefed + 1,
            })
        store.save(thread)
        saved.append(thread)
    return saved
