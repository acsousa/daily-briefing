"""Cluster, rank, continuity, plan, weather, editor, script — no network, stubbed LLM."""
import json
from datetime import date, datetime, timezone

from briefing.cluster import cluster_articles
from briefing.continuity import match_threads, update_threads
from briefing.editor import EditorOutput, edit_rundown
from briefing.ingest import make_article
from briefing.ingest.weather import get_forecast
from briefing.plan import build_plan
from briefing.rank import rank_clusters
from briefing.script import write_script
from briefing.store import Store, StoryThread

NOW = datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc)
TODAY = date(2026, 6, 18)

PROFILE = {
    "interests": [
        {"topic": "technology", "weight": 1.0, "keywords": ["Nvidia"]},
        {"topic": "defense", "weight": 1.0, "keywords": []},
    ],
    "must_cover": ["defense"],
    "limits": {"max_segments": 6},
    "style": {"tone": "concise", "inspirations": ["Marketplace"]},
}


def _art(id, title, topics, hours_ago=1):
    a = make_article(url=f"https://e.com/{id}", title=title, summary=f"{title} summary",
                     source_id="s", source_name="Src", topics=topics)
    return a.model_copy(update={
        "id": id,
        "published_at": NOW - __import__("datetime").timedelta(hours=hours_ago),
    })


def test_cluster_groups_similar_titles():
    arts = [
        _art("a", "Nvidia unveils new AI chip for data centers", ["technology"]),
        _art("b", "Nvidia's new AI chip targets data center growth", ["technology"]),
        _art("c", "Pentagon awards drone autonomy contract", ["defense"]),
    ]
    clusters = cluster_articles(arts)
    sizes = sorted(len(c.article_ids) for c in clusters)
    assert sizes == [1, 2]                      # the two Nvidia stories merged


def test_rank_orders_by_score_and_sets_components():
    arts = [_art("a", "Nvidia AI chip", ["technology"]),
            _art("c", "Pentagon drone contract", ["defense"], hours_ago=20)]
    ranked = rank_clusters(cluster_articles(arts), PROFILE, now=NOW)
    assert all(c.score is not None for c in ranked)
    assert ranked == sorted(ranked, key=lambda c: c.score, reverse=True)
    assert set(ranked[0].score_components) == {"freshness", "importance", "interest", "region", "novelty"}


def test_continuity_marks_developing_and_damps_novelty():
    arts = [_art("a", "Pentagon drone autonomy contract expands", ["defense"])]
    clusters = cluster_articles(arts)
    thread = StoryThread(id="t1", title="Pentagon drone autonomy contract", topic="defense",
                         first_briefed=date(2026, 6, 17), last_briefed=date(2026, 6, 17),
                         summary_so_far="DoD expanded its drone program.")
    windows = {"recent_days": 1, "week_days": 7, "month_days": 30}
    decisions = match_threads(clusters, [thread], TODAY, windows)
    d = decisions[clusters[0].id]
    assert d["status"] == "developing"
    assert d["novelty"] < 1.0
    assert d["recap"]


def test_plan_respects_duration_and_must_cover():
    arts = [_art("a", "Nvidia AI chip", ["technology"]),
            _art("c", "Pentagon drone contract", ["defense"], hours_ago=30)]
    ranked = rank_clusters(cluster_articles(arts), PROFILE, now=NOW)
    config = {"episode": {"target_duration_minutes": 10}, "spotify": {"show_id": "x"}}
    plan = build_plan(ranked, PROFILE, config, has_weather=True, today=TODAY)
    kinds = [s.kind for s in plan.segments]
    assert kinds[0] == "intro" and kinds[1] == "weather" and kinds[-1] == "outro"
    assert plan.target_duration_sec == 600
    # must_cover defense story is included even though older/lower-ranked
    headline_topics = {clusters_topic(ranked, s.story_cluster_id) for s in plan.segments if s.kind == "headline"}
    assert "defense" in headline_topics


def clusters_topic(clusters, cid):
    return next(c for c in clusters if c.id == cid).topics[0]


def test_weather_parse():
    payload = json.dumps({"daily": {
        "time": ["2026-06-18"], "temperature_2m_max": [82.4], "temperature_2m_min": [61.1],
        "precipitation_probability_max": [20], "weather_code": [2]}}).encode()
    wx = get_forecast(42.36, -71.06, fetcher=lambda url: payload)
    assert wx == {"high_f": 82, "low_f": 61, "precip_pct": 20, "conditions": "partly cloudy"}


class _StubLLM:
    """Stand-in for briefing.llm.LLM — no API calls."""
    default_model = "stub"
    editor_model = "stub"
    script_model = "stub"

    def parse(self, system, user, schema, model=None, max_tokens=16000):
        # one beat-brief per story_cluster_id present in the prompt
        ids = [json.loads(line)["story_cluster_id"] for line in user.splitlines()
               if line.strip().startswith("{")]
        Brief = schema.model_fields["segments"].annotation.__args__[0]
        return EditorOutput(through_line="Tech meets defense.", segments=[
            Brief(story_cluster_id=i, hook="hook", headline="The headline.",
                  what_happened="The facts.", why_it_matters="It matters.",
                  bridge="And next.", recap_line="")
            for i in ids])

    def complete(self, system, user, model=None, max_tokens=16000):
        return "AVA: Here is the news.\nANDREW: And here is what it means."


def test_editor_and_script_produce_grounded_segments(tmp_path):
    arts = [_art("a", "Nvidia AI chip for defense", ["technology", "defense"])]
    clusters = cluster_articles(arts)
    ranked = rank_clusters(clusters, PROFILE, now=NOW)
    config = {"episode": {"target_duration_minutes": 8}, "spotify": {"show_id": "x"}}
    plan = build_plan(ranked, PROFILE, config, has_weather=False, today=TODAY)
    clusters_by_id = {c.id: c for c in clusters}
    articles_by_id = {a.id: a for a in arts}
    decisions = match_threads(clusters, [], TODAY, {"month_days": 30})

    llm = _StubLLM()
    editor_output = edit_rundown(llm, plan, clusters_by_id, articles_by_id, decisions, PROFILE)
    assert editor_output.through_line

    text, segments, briefed = write_script(
        llm, plan, editor_output, clusters_by_id, articles_by_id, {}, PROFILE, None, TODAY)
    assert "AVA:" in text and "ANDREW:" in text
    headline_segs = [s for s in segments if s.kind == "headline"]
    assert headline_segs and headline_segs[0].source_attributions[0].url == "https://e.com/a"
    assert briefed                                 # feeds the continuity update

    store = Store(tmp_path / "t.db")
    update_threads(store, briefed, decisions, TODAY)
    assert len(store.list(StoryThread)) == 1       # new thread created
    store.close()
