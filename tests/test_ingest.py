"""Ingestion tests — fixture feeds only, no live network."""
from datetime import datetime, timezone
from pathlib import Path

from briefing.ingest import canonicalize_url, dedupe, filter_relevant, make_article
from briefing.ingest.feeds import FeedAdapter

FX = Path(__file__).parent / "fixtures"
PAST = datetime(2000, 1, 1, tzinfo=timezone.utc)
FUTURE = datetime(2100, 1, 1, tzinfo=timezone.utc)


def _fetcher(name):
    data = (FX / name).read_bytes()
    return lambda url: data


def _adapter(name, **cfg):
    base = {"id": "ex", "name": "Example", "type": "rss", "url": "x", "topics": ["technology"]}
    base.update(cfg)
    return FeedAdapter(base, fetcher=_fetcher(name))


def test_rss_parse_and_normalize():
    arts = _adapter("sample_rss.xml").fetch(PAST)
    assert len(arts) == 3
    a = arts[0]
    assert a.title == "AI chip breakthrough from Nvidia"
    assert a.canonical_url == "https://ex.com/a?id=5"   # utm_ dropped, id kept
    assert a.summary == "A new AI chip from Nvidia ships today."   # html stripped
    assert a.topics == ["technology"]
    assert a.source_name == "Example"


def test_json_feed_parse():
    arts = _adapter("sample_jsonfeed.json", type="json", topics=["robotics"]).fetch(PAST)
    assert len(arts) == 2
    assert arts[0].title == "Robotics startup raises a round"
    assert arts[0].content == "A humanoid robotics startup raised new funding."


def test_since_filter_drops_all():
    assert _adapter("sample_rss.xml").fetch(FUTURE) == []


def test_canonicalize_url():
    assert canonicalize_url("https://E.com/p/?utm_source=x&id=5#frag") == "https://e.com/p?id=5"


def test_dedupe_url_and_near_dup_title():
    a1 = make_article(url="https://ex.com/a?utm_source=x", title="AI chip breakthrough",
                      source_id="s1", source_name="S1", topics=["technology"])
    a2 = make_article(url="https://ex.com/a", title="AI chip breakthrough",
                      source_id="s2", source_name="S2", topics=["technology"])   # dup URL
    a3 = make_article(url="https://ex.com/b", title="AI chip breakthrough!",
                      source_id="s3", source_name="S3", topics=["technology"])   # near-dup title
    a4 = make_article(url="https://ex.com/c", title="A totally separate weather story",
                      source_id="s4", source_name="S4", topics=["world"])
    out = dedupe([a1, a2, a3, a4])
    assert [a.url for a in out] == ["https://ex.com/a?utm_source=x", "https://ex.com/c"]


def test_relevance_drops_only_avoided():
    # filter keeps everything not avoided (interest/region targeting happens later)
    profile = {"avoid": ["celebrity", "sports", "entertainment"]}
    tech = make_article(url="https://e.com/1", title="AI chip breakthrough",
                        summary="A new chip from Nvidia", source_id="s", source_name="S",
                        topics=["technology"])
    health = make_article(url="https://e.com/5", title="New study published",
                          summary="a study", source_id="s", source_name="S",
                          topics=["health"])                     # off-interest but NOT dropped
    celeb = make_article(url="https://e.com/3", title="Celebrity gossip",
                         summary="entertainment news", source_id="s", source_name="S",
                         topics=["entertainment"])               # avoided (text + topic)
    sports = make_article(url="https://e.com/4", title="Game recap", summary="final scores",
                          source_id="s", source_name="S", topics=["sports"])   # avoided by topic

    kept = filter_relevant([tech, health, celeb, sports], profile)
    assert {a.url for a in kept} == {"https://e.com/1", "https://e.com/5"}
    assert kept[0].topics == ["technology"]                     # source topics preserved
