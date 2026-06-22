"""Build an EpisodePlan: order segments to a duration budget from config."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

from ..store import EpisodePlan, PlannedSegment

INTRO_SEC = 25
WEATHER_SEC = 20            # shortened — weather is a quick note, not a segment
OUTRO_SEC = 20
LEAD_SHARE = 0.30          # the lead story gets a deeper treatment
LEAD_MAX_SEC = 300
QUICKHIT_MIN_SEC = 70      # the rest are tight hits
QUICKHIT_MAX_SEC = 160
TOP_SALIENT = 3            # always include this many of the biggest stories


def build_plan(ranked_clusters, profile, config, *, has_weather: bool, today: date,
               novelty_by_cluster: dict | None = None) -> EpisodePlan:
    target_sec = int(config.get("episode", {}).get("target_duration_minutes", 20)) * 60
    limits = profile.get("limits", {})
    max_segments = int(limits.get("max_segments", 8))
    must_cover = set(profile.get("must_cover", []))

    segments = [PlannedSegment(kind="intro", allotted_sec=INTRO_SEC)]
    if has_weather:
        segments.append(PlannedSegment(kind="weather", allotted_sec=WEATHER_SEC))

    fixed = sum(s.allotted_sec for s in segments) + OUTRO_SEC
    body_budget = max(target_sec - fixed, QUICKHIT_MIN_SEC)
    body_slots = max(max_segments - len(segments) - 1, 1)

    # never miss the day's biggest stories: guarantee the top few by coverage salience
    biggest = sorted(ranked_clusters, key=lambda c: (c.source_count, c.score or 0), reverse=True)
    guaranteed = {c.id for c in biggest[:TOP_SALIENT] if c.source_count >= 2}
    selected = _select(ranked_clusters, body_slots, body_budget, must_cover, guaranteed)
    if selected:
        # lead story deeper; the rest are tight quick hits
        lead_sec = min(int(body_budget * LEAD_SHARE), LEAD_MAX_SEC)
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


def _select(ranked, slots, budget, must_cover, guaranteed=frozenset()):
    """Pick clusters: biggest stories + must-cover first, then by rank, within slot caps."""
    chosen, seen = [], set()

    def take(c):
        chosen.append(c)
        seen.add(c.id)

    # the day's biggest stories (already in rank order) — never miss them
    for c in ranked:
        if len(chosen) >= slots:
            break
        if c.id in guaranteed and c.id not in seen:
            take(c)
    # must-cover topics
    for c in ranked:
        if len(chosen) >= slots:
            break
        if must_cover & set(c.topics) and c.id not in seen:
            take(c)
    # then top-ranked to fill remaining slots
    for c in ranked:
        if len(chosen) >= slots:
            break
        if c.id not in seen:
            take(c)
    # keep overall rank order so the highest-scored leads
    return sorted(chosen, key=lambda c: c.score or 0, reverse=True)
