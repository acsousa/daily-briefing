"""Full-text article extraction (the personal-reading content policy).

Fetches the article page and extracts the main body with trafilatura. Injectable
fetcher for tests; returns None when nothing usable is extracted.
"""
from __future__ import annotations

from .feeds import _http_get


def fetch_fulltext(url: str, fetcher=_http_get) -> str | None:
    import trafilatura
    try:
        html = fetcher(url)
    except Exception:
        return None
    if not html:
        return None
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    text = trafilatura.extract(html, include_comments=False, include_tables=False)
    return text or None
