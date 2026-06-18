"""Group RawArticles into StoryClusters by title/entity overlap (rule-based).

A hook for embedding similarity can replace `_similar` later without changing the
interface.
"""
from __future__ import annotations

import hashlib

from ..store import StoryCluster
from ..text import entities, jaccard, tokens

SIMILARITY_THRESHOLD = 0.34


def _similar(a_tokens: set[str], b_tokens: set[str]) -> bool:
    return jaccard(a_tokens, b_tokens) >= SIMILARITY_THRESHOLD


def cluster_articles(articles) -> list[StoryCluster]:
    groups: list[dict] = []
    for art in articles:
        tok = tokens(art.title)
        for g in groups:
            if _similar(tok, g["tokens"]):
                g["articles"].append(art)
                g["tokens"] |= tok
                break
        else:
            groups.append({"articles": [art], "tokens": set(tok)})
    return [_to_cluster(g["articles"]) for g in groups]


def _to_cluster(arts) -> StoryCluster:
    arts = sorted(arts, key=lambda a: a.published_at, reverse=True)
    rep = max(arts, key=lambda a: len(a.title))          # fullest headline
    topics = sorted({t for a in arts for t in a.topics})
    ents = entities(" . ".join(a.title for a in arts))
    cid = hashlib.sha256("|".join(sorted(a.id for a in arts)).encode()).hexdigest()[:16]
    return StoryCluster(
        id=cid,
        title=rep.title,
        article_ids=[a.id for a in arts],
        topics=topics,
        entities=ents,
        first_seen=min(a.published_at for a in arts),
        last_updated=max(a.published_at for a in arts),
        score_components={},
    )
