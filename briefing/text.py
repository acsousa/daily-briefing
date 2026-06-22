"""Tiny text helpers shared by clustering and continuity matching."""
from __future__ import annotations

import re

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for", "with",
    "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "it",
    "its", "this", "that", "these", "those", "new", "says", "say", "after",
    "over", "amid", "into", "out", "up", "down", "how", "why", "what", "us",
}


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def entities(text: str) -> list[str]:
    """Individual capitalized words (proper-noun-ish), for cross-source story matching.

    Individual tokens (not greedy phrases) so 'Alan Greenspan Dies' and 'Alan Greenspan,
    the ...' share {Alan, Greenspan} regardless of title-case vs sentence-case headlines.
    """
    seen, out = set(), []
    for w in re.findall(r"\b[A-Z][a-zA-Z]+\b", text or ""):
        wl = w.lower()
        if len(w) > 2 and wl not in _STOPWORDS and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:15]
