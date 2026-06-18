from .base import SourceAdapter, make_article
from .dedupe import canonicalize_url, dedupe
from .feeds import FeedAdapter
from .relevance import filter_relevant

__all__ = [
    "SourceAdapter",
    "make_article",
    "FeedAdapter",
    "canonicalize_url",
    "dedupe",
    "filter_relevant",
]
