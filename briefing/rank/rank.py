"""Score StoryClusters by freshness, importance, interest match, and novelty."""
from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_WEIGHTS = {"freshness": 0.30, "importance": 0.25, "interest": 0.30, "novelty": 0.15}


def _freshness(cluster, now: datetime) -> float:
    hours = max((now - cluster.last_updated).total_seconds() / 3600.0, 0.0)
    # 1.0 fresh, ~0.5 at 12h, decaying toward 0 across a day
    return 1.0 / (1.0 + hours / 12.0)


def _importance(cluster) -> float:
    return min(len(cluster.article_ids) / 3.0, 1.0)   # corroboration across sources


def _interest(cluster, profile) -> float:
    weights = {i["topic"]: i.get("weight", 0.0) for i in profile.get("interests", [])}
    return max((weights.get(t, 0.0) for t in cluster.topics), default=0.0)


def rank_clusters(clusters, profile, weights=None, novelty_by_cluster=None, now=None):
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    novelty_by_cluster = novelty_by_cluster or {}
    now = now or datetime.now(timezone.utc)
    for c in clusters:
        comp = {
            "freshness": _freshness(c, now),
            "importance": _importance(c),
            "interest": _interest(c, profile),
            "novelty": novelty_by_cluster.get(c.id, 1.0),
        }
        c.score = sum(w[k] * comp[k] for k in comp)
        c.score_components = comp
    return sorted(clusters, key=lambda c: c.score or 0.0, reverse=True)
