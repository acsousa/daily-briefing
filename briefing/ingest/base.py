"""SourceAdapter interface + RawArticle normalization."""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from ..store import RawArticle
from .dedupe import canonicalize_url


def _hash(*parts: str) -> str:
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()


def make_article(*, url, title, source_id, source_name, topics,
                 summary=None, content=None, author=None,
                 published_at=None, language=None, raw=None) -> RawArticle:
    """Normalize raw fields into a RawArticle with a stable id + content hash."""
    title = (title or "").strip()
    canonical = canonicalize_url(url)
    now = datetime.now(timezone.utc)
    return RawArticle(
        id=_hash(canonical)[:16],
        url=url,
        canonical_url=canonical,
        title=title,
        summary=summary,
        content=content,
        author=author,
        source_id=source_id,
        source_name=source_name,
        topics=list(topics),
        published_at=published_at or now,
        fetched_at=now,
        content_hash=_hash(title, summary or content or "")[:16],
        language=language,
        raw=raw or {},
    )


class SourceAdapter(ABC):
    def __init__(self, source_id: str, source_name: str, topics: list[str]):
        self.source_id = source_id
        self.source_name = source_name
        self.topics = list(topics)

    @abstractmethod
    def fetch(self, since: datetime) -> list[RawArticle]:
        """Return articles published at/after `since`."""
