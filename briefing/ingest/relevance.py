"""Drop only what the user wants to avoid; keep everything else.

Interest/region targeting happens later, in ranking and selection — NOT here — so the
day's biggest stories survive ingestion even if they don't match an interest topic (they
get surfaced by coverage salience). Only the `avoid` list removes articles outright.
"""
from __future__ import annotations


def _is_avoided(article, avoid: list[str]) -> bool:
    text = f"{article.title} {article.summary or ''}".lower()
    src_topics = {t.lower() for t in article.topics}
    return any(term in text or term in src_topics for term in avoid)


def filter_relevant(articles, profile: dict):
    """Keep articles not matching the profile's avoid list (source topics preserved)."""
    avoid = [a.lower() for a in profile.get("avoid", [])]
    return [a for a in articles if not _is_avoided(a, avoid)]
