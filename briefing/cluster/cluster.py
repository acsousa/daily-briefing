"""Group RawArticles into StoryClusters by title + entity overlap (rule-based).

Cross-source merging matters for salience: when many outlets cover the same event, those
articles must land in one cluster so coverage volume (distinct sources) is measurable. We
merge on token overlap OR shared named entities, so differently-worded headlines about the
same story still join.
"""
from __future__ import annotations

import hashlib
from collections import Counter

from ..store import StoryCluster
from ..text import entities, jaccard, tokens

TOKEN_THRESHOLD = 0.28          # strong title-wording overlap
SOFT_TOKEN_THRESHOLD = 0.15     # weaker wording overlap, needs entity backing
SHARED_ENTITIES = 2             # this many shared proper nouns merges differently-worded heds


def _matches(group, tok, ents) -> bool:
    j = jaccard(tok, group["tokens"])
    if j >= TOKEN_THRESHOLD:
        return True
    return j >= SOFT_TOKEN_THRESHOLD and len(ents & group["entities"]) >= SHARED_ENTITIES


def cluster_articles(articles) -> list[StoryCluster]:
    groups: list[dict] = []
    for art in articles:
        tok = tokens(art.title)
        ents = set(entities(art.title))
        for g in groups:
            if _matches(g, tok, ents):
                g["articles"].append(art)
                g["tokens"] |= tok
                g["entities"] |= ents
                break
        else:
            groups.append({"articles": [art], "tokens": set(tok), "entities": set(ents)})
    return [_to_cluster(g["articles"]) for g in groups]


def _to_cluster(arts) -> StoryCluster:
    arts = sorted(arts, key=lambda a: a.published_at, reverse=True)
    rep = max(arts, key=lambda a: len(a.title))          # fullest headline
    topic_counts = Counter(t for a in arts for t in a.topics)
    topics = sorted(topic_counts)
    ents = entities(" . ".join(a.title for a in arts))
    sources = {a.source_id for a in arts}
    cid = hashlib.sha256("|".join(sorted(a.id for a in arts)).encode()).hexdigest()[:16]
    return StoryCluster(
        id=cid,
        title=rep.title,
        article_ids=[a.id for a in arts],
        topics=topics,
        topic_counts=dict(topic_counts),
        entities=ents,
        source_count=len(sources),
        first_seen=min(a.published_at for a in arts),
        last_updated=max(a.published_at for a in arts),
        score_components={},
    )
