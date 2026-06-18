"""Round-trip each model through the SQLite store."""
from datetime import date, datetime

import pytest

from briefing.store import (
    EpisodePlan,
    EpisodeSegment,
    InteractionContext,
    PlannedSegment,
    RawArticle,
    SourceAttribution,
    Store,
    StoryCluster,
)

DT = datetime(2026, 6, 18, 5, 0, 0)


def _samples():
    article = RawArticle(
        id="a1", url="https://ex.com/x?utm_source=rss", canonical_url="https://ex.com/x",
        title="Headline", summary="sum", content="full body", author="A. Writer",
        source_id="ex", source_name="Example", topics=["tech_big", "robotics"],
        published_at=DT, fetched_at=DT, content_hash="deadbeef", language="en",
        raw={"k": "v", "n": 1},
    )
    cluster = StoryCluster(
        id="c1", title="Cluster", summary=None, article_ids=["a1", "a2"],
        topics=["tech_big"], entities=["Nvidia"], first_seen=DT, last_updated=DT,
        score=0.87, score_components={"freshness": 0.9, "interest": 1.0},
    )
    plan = EpisodePlan(
        id="e1", date=date(2026, 6, 18), target_duration_sec=1200,
        segments=[PlannedSegment(kind="weather", allotted_sec=30),
                  PlannedSegment(kind="headline", story_cluster_id="c1", allotted_sec=120)],
        status="planned", show_id="spotify:show:abc", created_at=DT,
    )
    segment = EpisodeSegment(
        id="s1", episode_id="e1", order_index=2, kind="headline", story_cluster_id="c1",
        script="ARIA: Hello.\nANDREW: Hi.",
        source_attributions=[SourceAttribution(article_id="a1", url="https://ex.com/x", title="Headline")],
        audio_offset_sec=12.5, start_time=12.5, end_time=130.0,
    )
    interaction = InteractionContext(
        id="i1", episode_id="e1", segment_id="s1", timestamp_sec=42.0,
        question="Why does it matter?", intent="implications", answer="Because...",
        answer_sources=[SourceAttribution(article_id="a1", url="https://ex.com/x", title="Headline")],
        created_at=DT,
    )
    return [article, cluster, plan, segment, interaction]


@pytest.mark.parametrize("obj", _samples(), ids=lambda o: type(o).__name__)
def test_round_trip(tmp_path, obj):
    store = Store(tmp_path / "test.db")
    store.save(obj)
    loaded = store.get(type(obj), obj.id)
    assert loaded == obj
    store.close()


def test_list_and_filter(tmp_path):
    store = Store(tmp_path / "test.db")
    store.save_many(_samples())
    assert len(store.list(RawArticle)) == 1
    assert store.list(RawArticle, source_id="ex")[0].id == "a1"
    assert store.list(RawArticle, source_id="missing") == []
    assert store.list(EpisodeSegment, episode_id="e1")[0].order_index == 2
    store.close()


def test_upsert_replaces(tmp_path):
    store = Store(tmp_path / "test.db")
    a = _samples()[0]
    store.save(a)
    store.save(a.model_copy(update={"title": "Updated"}))
    assert len(store.list(RawArticle)) == 1
    assert store.get(RawArticle, "a1").title == "Updated"
    store.close()


def test_get_missing_returns_none(tmp_path):
    store = Store(tmp_path / "test.db")
    assert store.get(RawArticle, "nope") is None
    store.close()
