"""Interest-first planning: top-interest coverage, event de-dup, genuine topic matching,
and length-proportional lead sizing. Mirrors the real 'two World Cup stories' regression."""
from datetime import date, datetime, timezone

from briefing.plan import build_plan
from briefing.plan.plan import _genuine, _rotate, _same_event, _select
from briefing.store import StoryCluster

NOW = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 6, 25)

PROFILE = {
    "interests": [
        {"topic": "technology", "weight": 1.0, "keywords": ["AI", "software", "hardware"]},
        {"topic": "business", "weight": 1.0, "keywords": ["markets", "economy", "earnings"]},
        {"topic": "defense", "weight": 1.0, "keywords": []},
        {"topic": "science", "weight": 0.5, "keywords": ["space", "research"]},
        {"topic": "world", "weight": 0.5, "keywords": []},
    ],
    "must_cover": [],
    "limits": {"max_segments": 8},
}


def C(cid, title, counts, source_count, score):
    return StoryCluster(id=cid, title=title, topics=sorted(counts), topic_counts=counts,
                        source_count=source_count, score=score, first_seen=NOW, last_updated=NOW)


def _day():
    # the uploaded episode's day, modeled as clusters (score desc handled by _select)
    return [
        C("hormuz", "Iran tightens grip on Strait of Hormuz sending oil higher",
          {"business": 1, "politics": 1, "world": 1}, 3, 0.90),
        C("wc_stream", "How the World Cup became a US streaming success story",
          {"sports": 2, "technology": 1, "world": 1}, 4, 0.85),
        C("wc_match", "Spain vs Uruguay at World Cup 2026 knockouts",
          {"sports": 2, "world": 1}, 3, 0.70),
        C("scotus", "Supreme Court blocks asylum seekers at the border",
          {"world": 1, "politics": 1}, 3, 0.65),
        C("supp", "White House sends 87.6B supplemental for defense and Ebola",
          {"defense": 1, "health": 1, "politics": 1}, 2, 0.60),
        C("tech", "Nvidia unveils new AI chip for data centers",
          {"technology": 2}, 2, 0.55),
        C("science", "NASA telescope spots a distant galaxy",
          {"science": 2}, 2, 0.40),
    ]


def test_no_duplicate_event_and_interest_coverage():
    selected = _select(_day(), 5, PROFILE, TODAY)
    ids = [c.id for c in selected]

    assert len(ids) == 5                                   # fills the slots
    assert not ("wc_stream" in ids and "wc_match" in ids)  # never two World Cup stories
    assert "wc_match" not in ids                           # the duplicate is the one dropped
    assert "tech" in ids        # the real tech story fills the tech slot, not the WC-tagged-tech
    assert "supp" in ids        # defense gets a slot (not covered by the biggest)
    # business is covered by the biggest (hormuz) so it doesn't claim a separate slot
    assert "hormuz" in ids
    # highest-scored leads
    assert selected[0].id == "hormuz"


def test_genuine_rejects_tagged_but_off_topic():
    clusters = {c.id: c for c in _day()}
    tech = {"topic": "technology", "keywords": ["AI", "software", "hardware"]}
    # World Cup carried a 'technology' tag (one outlet) but isn't genuinely tech
    assert _genuine(clusters["wc_stream"], tech) is False
    assert _genuine(clusters["tech"], tech) is True
    # business is one of hormuz's co-dominant topics -> genuine
    assert _genuine(clusters["hormuz"], {"topic": "business", "keywords": []}) is True


def test_same_event_detects_shared_headline_terms():
    day = {c.id: c for c in _day()}
    assert _same_event(day["wc_stream"], day["wc_match"]) is True     # share "world","cup"
    assert _same_event(day["hormuz"], day["scotus"]) is False


def test_reserves_two_biggest_then_interests():
    # the two most-covered (wc_stream=4, hormuz=3) are always present
    ids = [c.id for c in _select(_day(), 5, PROFILE, TODAY)]
    assert "wc_stream" in ids and "hormuz" in ids


def test_broad_interests_rotate_by_date():
    broad = [{"topic": "science"}, {"topic": "world"}, {"topic": "health"}]
    a = [i["topic"] for i in _rotate(broad, date(2026, 6, 25))]
    b = [i["topic"] for i in _rotate(broad, date(2026, 6, 26))]
    assert a != b and sorted(a) == sorted(b)               # same set, rotated order


def test_lead_cap_scales_with_episode_length():
    day = _day()
    ranked = sorted(day, key=lambda c: c.score, reverse=True)
    lead25 = next(s.allotted_sec for s in build_plan(
        ranked, PROFILE, {"episode": {"target_duration_minutes": 25}},
        has_weather=True, today=TODAY).segments if s.kind == "headline")
    lead20 = next(s.allotted_sec for s in build_plan(
        ranked, PROFILE, {"episode": {"target_duration_minutes": 20}},
        has_weather=True, today=TODAY).segments if s.kind == "headline")
    assert lead25 == 300            # 20% of 1500s
    assert lead20 == 240            # 20% of 1200s
    # at least 5 stories fit a 25-min episode
    headlines = [s for s in build_plan(
        ranked, PROFILE, {"episode": {"target_duration_minutes": 25}},
        has_weather=True, today=TODAY).segments if s.kind == "headline"]
    assert len(headlines) >= 5
