"""Score StoryClusters by freshness, coverage salience, interest, region, novelty."""
from __future__ import annotations

from datetime import datetime, timezone

DEFAULT_WEIGHTS = {"freshness": 0.22, "importance": 0.28, "interest": 0.30,
                   "region": 0.12, "novelty": 0.08}
OFF_FOCUS_DAMP = 0.7       # soft de-emphasis for stories outside the user's interests
                          # (not avoided — they can still surface if genuinely dominant)

# Coarse region keyword signals — used only to nudge ranking, not to hard-filter.
REGION_TERMS = {
    "U.S.": ["u.s.", "united states", "america", "washington", "congress", "white house",
             "pentagon", "federal reserve", "wall street"],
    "Europe": ["europe", "european", "brussels", "britain", "uk", "france", "germany",
               "ukraine", "russia", "nato"],
    "Canada": ["canada", "canadian", "ottawa"],
    "South America": ["brazil", "argentina", "chile", "colombia", "venezuela",
                      "latin america", "south america"],
    "Asia": ["china", "chinese", "japan", "korea", "india", "asia", "beijing",
             "tokyo", "taiwan"],
}


def _freshness(cluster, now: datetime) -> float:
    hours = max((now - cluster.last_updated).total_seconds() / 3600.0, 0.0)
    return 1.0 / (1.0 + hours / 12.0)


def _importance(cluster) -> float:
    # coverage salience: how many distinct sources are covering this story
    return min(cluster.source_count / 3.0, 1.0)


def _interest(cluster, profile) -> float:
    weights = {i["topic"]: i.get("weight", 0.0) for i in profile.get("interests", [])}
    best = max((weights.get(t, 0.0) for t in cluster.topics), default=0.0)
    text = f"{cluster.title} {cluster.summary or ''}".lower()
    for i in profile.get("interests", []):                # keyword match can raise it
        w = i.get("weight", 0.0)
        if w > best and any(k.lower() in text for k in i.get("keywords", [])):
            best = w
    return best


def _region(cluster, profile) -> float:
    regions = profile.get("regions") or ["U.S."]
    text = f"{cluster.title} {cluster.summary or ''}".lower()
    selected = any(any(term in text for term in REGION_TERMS.get(r, [])) for r in regions)
    if selected:
        return 1.0
    foreign = any(any(term in text for term in terms)
                  for r, terms in REGION_TERMS.items() if r not in regions)
    return 0.45 if foreign else 0.85     # clearly-foreign down-weighted; neutral stays high


def rank_clusters(clusters, profile, weights=None, novelty_by_cluster=None, now=None):
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    novelty_by_cluster = novelty_by_cluster or {}
    now = now or datetime.now(timezone.utc)
    for c in clusters:
        comp = {
            "freshness": _freshness(c, now),
            "importance": _importance(c),
            "interest": _interest(c, profile),
            "region": _region(c, profile),
            "novelty": novelty_by_cluster.get(c.id, 1.0),
        }
        score = sum(w.get(k, 0.0) * v for k, v in comp.items())
        if comp["interest"] == 0.0:           # outside your focus → softly de-emphasized
            score *= OFF_FOCUS_DAMP
        c.score = score
        c.score_components = comp
    return sorted(clusters, key=lambda c: c.score or 0.0, reverse=True)
