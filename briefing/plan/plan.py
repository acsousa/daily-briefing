"""Build an EpisodePlan: order segments to a duration budget from config.

Story selection favors the listener's interests over raw coverage so the briefing isn't
just "the most-covered headlines." The recipe per episode:
  1. reserve a couple of slots for the day's biggest stories (coverage salience),
  2. give each top interest its own slot — unless a biggest story already covers it,
  3. fill the rest from broader interests on a date-rotated basis (so they take turns),
  4. backstop with top-ranked stories to reach the slot count.
Stories about the same event are de-duplicated, and a topic only counts toward an interest
when the story is genuinely about it (not just tangentially tagged by one outlet).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone

from ..store import EpisodePlan, PlannedSegment

INTRO_SEC = 25
WEATHER_SEC = 20            # shortened — weather is a quick note, not a segment
OUTRO_SEC = 20
LEAD_SHARE = 0.30          # the lead story gets a deeper treatment (share of the body budget)
LEAD_MAX_FRACTION = 0.20   # ...but never more than this share of the whole episode (300s @ 25min)
QUICKHIT_MIN_SEC = 70      # the rest are tight hits
QUICKHIT_MAX_SEC = 160
NUM_BIGGEST = 2            # reserve this many slots for the day's most-covered stories
MIN_SALIENT_SOURCES = 2   # ...each needs at least this many distinct sources to qualify
TOP_INTEREST_WEIGHT = 1.0 # interests at/above this weight are "headline focus"
SAME_EVENT_SHARED_TERMS = 2  # two stories sharing this many salient title terms = same event

_STOP = {"the", "and", "or", "of", "to", "in", "on", "for", "with", "at", "by", "from", "as",
         "is", "are", "was", "were", "be", "new", "how", "why", "what", "this", "that", "over",
         "into", "amid", "after", "before", "its", "their", "his", "her", "you", "your", "more",
         "than", "but", "not", "out", "up", "down", "off", "now", "has", "had", "who", "did",
         "get", "got", "can", "all", "one", "two", "day", "set", "say", "says", "said", "amid"}


def _title_terms(c) -> set:
    # 3+ char tokens so short-but-distinctive words (e.g. "cup", "oil", "war") still count
    return {w for w in re.findall(r"[a-z0-9]{3,}", (c.title or "").lower()) if w not in _STOP}


def _same_event(a, b) -> bool:
    # same story if titles share enough salient terms, or they share a named entity
    if len(_title_terms(a) & _title_terms(b)) >= SAME_EVENT_SHARED_TERMS:
        return True
    ea, eb = set(getattr(a, "entities", []) or []), set(getattr(b, "entities", []) or [])
    return bool(ea & eb)


def _is_dup(c, chosen) -> bool:
    return any(_same_event(c, x) for x in chosen)


def _plurality_topics(c) -> set:
    counts = getattr(c, "topic_counts", None) or {}
    if not counts:
        return set(c.topics or [])
    top = max(counts.values())
    return {t for t, n in counts.items() if n == top}


def _genuine(c, interest) -> bool:
    """Is the cluster genuinely about this interest's topic — not just tagged by one outlet?
    True when the topic is (one of) the cluster's dominant topics, or an interest keyword hits."""
    topic = interest["topic"]
    if topic not in (c.topics or []):
        return False
    if topic in _plurality_topics(c):
        return True
    text = f"{c.title} {c.summary or ''}".lower()
    return any(k.lower() in text for k in (interest.get("keywords") or []))


def _best_for(interest, ranked, seen, chosen):
    """Highest-ranked unused, non-duplicate cluster genuinely about this interest."""
    for c in ranked:                       # ranked is already score-sorted
        if c.id in seen or _is_dup(c, chosen):
            continue
        if _genuine(c, interest):
            return c
    return None


def _rotate(items, today: date):
    if not items:
        return items
    k = today.toordinal() % len(items)
    return items[k:] + items[:k]


def build_plan(ranked_clusters, profile, config, *, has_weather: bool, today: date,
               novelty_by_cluster: dict | None = None) -> EpisodePlan:
    target_sec = int(config.get("episode", {}).get("target_duration_minutes", 20)) * 60
    limits = profile.get("limits", {})
    max_segments = int(limits.get("max_segments", 8))

    segments = [PlannedSegment(kind="intro", allotted_sec=INTRO_SEC)]
    if has_weather:
        segments.append(PlannedSegment(kind="weather", allotted_sec=WEATHER_SEC))

    fixed = sum(s.allotted_sec for s in segments) + OUTRO_SEC
    body_budget = max(target_sec - fixed, QUICKHIT_MIN_SEC)
    body_slots = max(max_segments - len(segments) - 1, 1)

    selected = _select(ranked_clusters, body_slots, profile, today)
    if selected:
        # lead story deeper; the rest are tight quick hits. Lead is capped by episode length.
        lead_sec = min(int(body_budget * LEAD_SHARE), int(target_sec * LEAD_MAX_FRACTION))
        segments.append(PlannedSegment(
            kind="headline", story_cluster_id=selected[0].id, allotted_sec=lead_sec))
        rest = selected[1:]
        if rest:
            per = (body_budget - lead_sec) // len(rest)
            per = max(min(per, QUICKHIT_MAX_SEC), QUICKHIT_MIN_SEC)
            for c in rest:
                segments.append(PlannedSegment(
                    kind="headline", story_cluster_id=c.id, allotted_sec=per))

    segments.append(PlannedSegment(kind="outro", allotted_sec=OUTRO_SEC))

    pid = hashlib.sha256(f"{today}".encode()).hexdigest()[:16]
    return EpisodePlan(
        id=pid,
        date=today,
        target_duration_sec=target_sec,
        segments=segments,
        status="planned",
        show_id=config.get("spotify", {}).get("show_id"),
        created_at=datetime.now(timezone.utc),
    )


def _select(ranked, slots, profile, today: date):
    """Interest-first selection: biggest stories, then top interests (unless already covered),
    then broader interests on rotation, then a top-ranked backstop. De-duped by event."""
    interests = profile.get("interests") or []
    top = [i for i in interests if i.get("weight", 0) >= TOP_INTEREST_WEIGHT]
    broad = [i for i in interests if 0 < i.get("weight", 0) < TOP_INTEREST_WEIGHT]
    must_cover = list(profile.get("must_cover") or [])

    chosen, seen = [], set()

    def take(c):
        chosen.append(c)
        seen.add(c.id)

    # 1. the day's biggest stories by coverage salience, event-deduped
    biggest = sorted(ranked, key=lambda c: (c.source_count, c.score or 0), reverse=True)
    for c in biggest:
        if len(chosen) >= min(NUM_BIGGEST, slots):
            break
        if c.id not in seen and c.source_count >= MIN_SALIENT_SOURCES and not _is_dup(c, chosen):
            take(c)

    # 2. explicit must-cover topics
    for topic in must_cover:
        if len(chosen) >= slots:
            break
        c = _best_for({"topic": topic, "keywords": []}, ranked, seen, chosen)
        if c:
            take(c)

    # 3. one slot per top interest — unless a story already chosen genuinely covers it
    for interest in top:
        if len(chosen) >= slots:
            break
        if any(_genuine(c, interest) for c in chosen):
            continue
        c = _best_for(interest, ranked, seen, chosen)
        if c:
            take(c)

    # 4. fill the remainder from broader interests on a date rotation (they take turns)
    for interest in _rotate(broad, today):
        if len(chosen) >= slots:
            break
        c = _best_for(interest, ranked, seen, chosen)
        if c:
            take(c)

    # 5. backstop: reach the slot count with the best remaining non-duplicate stories
    for c in ranked:
        if len(chosen) >= slots:
            break
        if c.id not in seen and not _is_dup(c, chosen):
            take(c)

    # keep overall rank order so the highest-scored leads
    return sorted(chosen, key=lambda c: c.score or 0, reverse=True)
