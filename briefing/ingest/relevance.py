"""Keep only articles relevant to the active user profile.

An article is relevant if its source topics intersect the profile's active topics
(weight > 0) OR an interest keyword appears in its title/summary. Anything matching
the `avoid` list (by text or source topic) is dropped first. Kept articles are
retagged with the matched profile topics for downstream clustering/ranking.
"""
from __future__ import annotations


def _active_topics(profile: dict) -> set[str]:
    return {i["topic"] for i in profile.get("interests", []) if i.get("weight", 0) > 0}


def _keyword_topics(profile: dict):
    return [
        (i["topic"], [k.lower() for k in i.get("keywords", [])])
        for i in profile.get("interests", [])
        if i.get("weight", 0) > 0
    ]


def _is_avoided(article, avoid: list[str]) -> bool:
    text = f"{article.title} {article.summary or ''}".lower()
    src_topics = {t.lower() for t in article.topics}
    return any(term in text or term in src_topics for term in avoid)


def filter_relevant(articles, profile: dict):
    avoid = [a.lower() for a in profile.get("avoid", [])]
    active = _active_topics(profile)
    keyword_topics = _keyword_topics(profile)
    kept = []
    for a in articles:
        if _is_avoided(a, avoid):
            continue
        text = f"{a.title} {a.summary or ''}".lower()
        matched = {t for t in a.topics if t in active}
        for topic, keywords in keyword_topics:
            if any(kw in text for kw in keywords):
                matched.add(topic)
        if matched:
            a.topics = sorted(matched)
            kept.append(a)
    return kept
