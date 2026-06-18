"""URL canonicalization + duplicate / near-duplicate removal."""
from __future__ import annotations

import difflib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_PREFIXES = ("utm_",)
_TRACKING_EXACT = {"fbclid", "gclid", "mc_cid", "mc_eid", "igshid"}


def canonicalize_url(url: str) -> str:
    """Lowercase scheme/host, drop tracking params and fragments, trim trailing slash."""
    parts = urlsplit((url or "").strip())
    query = [
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_EXACT
        and not any(k.lower().startswith(p) for p in _TRACKING_PREFIXES)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def _norm_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", title.lower())).strip()


def dedupe(articles, title_threshold: float = 0.85):
    """Drop exact URL duplicates and near-duplicate titles, keeping first seen."""
    seen_urls: set[str] = set()
    norm_titles: list[str] = []
    kept = []
    for a in articles:
        cu = a.canonical_url or canonicalize_url(a.url)
        if cu in seen_urls:
            continue
        nt = _norm_title(a.title)
        if nt and any(
            difflib.SequenceMatcher(None, nt, prev).ratio() > title_threshold
            for prev in norm_titles
        ):
            continue
        seen_urls.add(cu)
        norm_titles.append(nt)
        kept.append(a)
    return kept
