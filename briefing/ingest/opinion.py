"""Detect advice columns / opinion pieces so they don't surface as news.

A morning news briefing shouldn't lead with "I'm 70, a relative offered me a $25k loan…".
These are personal-finance/advice columns and op-eds, not reported news — drop them.
"""
from __future__ import annotations

import re

# First-person advice/essay openers (headlines that are a personal question or story).
_FIRST_PERSON = re.compile(r"^\s*(i['’]m\b|i am\b|my\b|dear\b|ask\b|should i\b|how i\b|why i\b)", re.I)

_ADVICE_TERMS = (
    "moneyist", "dear abby", "ask the", "advice column", "my husband", "my wife",
    "my son", "my daughter", "my mother", "my father", "my brother", "my sister",
    "my relative", "my boyfriend", "my girlfriend", "my partner", "my neighbor",
    "i inherited", "i'm retired", "i'm 6", "i'm 7", "i'm 8",
)
_URL_MARKERS = ("/opinion/", "/advice/", "/columnist", "/columns/", "/voices/",
                "moneyist", "/perspective/", "/commentary/")


def _norm(s: str) -> str:
    # straighten curly quotes so "I'm 60" matches "i'm 6"
    return (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def is_opinion(article) -> bool:
    title = _norm(article.title or "")
    text = title.lower()
    url = (article.canonical_url or article.url or "").lower()
    if any(m in url for m in _URL_MARKERS):
        return True
    head = re.sub(r"^[\s\"'`]+", "", title)        # ignore a leading quote on quoted heds
    if _FIRST_PERSON.match(head):
        return True
    return any(term in text for term in _ADVICE_TERMS)
