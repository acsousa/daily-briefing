"""RSS/Atom + JSON Feed adapter behind SourceAdapter.

The HTTP fetch is injectable (`fetcher`) so tests run against fixtures with no network.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import feedparser
import httpx

from .base import SourceAdapter, make_article


# Some publishers 403 non-browser clients; present browser-like headers (common for feed
# readers). Personal reading — see memory: personal-reading-content-policy. Note: this won't
# get past hard bot-protection (Cloudflare) or an IP-level block — those feeds just skip.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _http_get(url: str) -> bytes:
    r = httpx.get(url, timeout=20, follow_redirects=True, headers=_HEADERS)
    if r.status_code in (401, 403, 429):     # publisher is blocking automated access
        raise RuntimeError(
            f"{r.status_code} {r.reason_phrase} — publisher blocked automated access; "
            "skipped (consider removing this feed)")
    r.raise_for_status()
    return r.content


def _strip_html(text: str | None) -> str | None:
    if not text:
        return text
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


def _rss_dt(entry) -> datetime:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return datetime.now(timezone.utc)


def _iso_dt(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class FeedAdapter(SourceAdapter):
    def __init__(self, cfg: dict, fetcher=_http_get):
        super().__init__(cfg["id"], cfg["name"], cfg.get("topics", []))
        self.url = cfg["url"]
        self.type = cfg.get("type", "rss")
        self.fetcher = fetcher

    def fetch(self, since: datetime):
        raw = self.fetcher(self.url)
        items = self._parse_json(raw) if self.type == "json" else self._parse_rss(raw)
        return [a for a in items if a.published_at >= since]

    def _parse_rss(self, raw):
        feed = feedparser.parse(raw)
        return [
            make_article(
                url=e.get("link") or "",
                title=e.get("title") or "",
                summary=_strip_html(e.get("summary")),
                author=e.get("author"),
                published_at=_rss_dt(e),
                source_id=self.source_id,
                source_name=self.source_name,
                topics=self.topics,
                raw={"feed_type": "rss"},
            )
            for e in feed.entries
        ]

    def _parse_json(self, raw):
        data = json.loads(raw)
        out = []
        for it in data.get("items", []):
            text = it.get("content_text") or _strip_html(it.get("content_html"))
            out.append(make_article(
                url=it.get("url") or "",
                title=it.get("title") or "",
                summary=it.get("summary") or text,
                content=text,
                author=(it.get("author") or {}).get("name"),
                published_at=_iso_dt(it.get("date_published")),
                source_id=self.source_id,
                source_name=self.source_name,
                topics=self.topics,
                raw={"feed_type": "json"},
            ))
        return out
