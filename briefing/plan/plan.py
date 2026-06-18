"""Build an EpisodePlan: order segments to a duration budget from config."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone

from ..store import EpisodePlan, PlannedSegment

INTRO_SEC = 25
WEATHER_SEC = 35
OUTRO_SEC = 20
MIN_BODY_SEC = 75            # floor per headline segment


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
    body_budget = max(target_sec - fixed, MIN_BODY_SEC)
    body_slots = max(max_segments - len(segments) - 1, 1)

    selected = _select(ranked_clusters, body_slots, body_budget, must_cover)
    total_score = sum((c.score or 0.01) for c in selected) or 1.0
    for c in selected:
        share = (c.score or 0.01) / total_score
        allotted = max(int(body_budget * share), MIN_BODY_SEC)
        segments.append(PlannedSegment(
            kind="headline", story_cluster_id=c.id, allotted_sec=allotted))

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


def _select(ranked, slots, budget, must_cover):
    """Pick clusters: must-cover topics first, then by rank, fitting slot/budget caps."""
    chosen, seen = [], set()
    # must-cover first
    for c in ranked:
        if len(chosen) >= slots:
            break
        if must_cover & set(c.topics) and c.id not in seen:
            chosen.append(c)
            seen.add(c.id)
    # then top-ranked to fill remaining slots
    for c in ranked:
        if len(chosen) >= slots:
            break
        if c.id not in seen:
            chosen.append(c)
            seen.add(c.id)
    return chosen
