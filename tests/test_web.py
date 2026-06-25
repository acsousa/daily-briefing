"""SIGNAL config-page mapping: form <-> YAML, patch-preserving."""
from briefing.web.app import TONE_PRESETS, form_to_yaml, yaml_to_form


def test_yaml_to_form_projects_values():
    profile = {
        "owner": {"name": "Andrew Sousa"},
        "interests": [{"topic": "technology", "weight": 1.0}, {"topic": "defense", "weight": 1.0},
                      {"topic": "business", "weight": 0.9}, {"topic": "science", "weight": 0.4}],
        "avoid": ["sports"], "must_cover": ["earnings"],
        "style": {"playfulness": 40, "tone": "rich paragraph"},
    }
    config = {"episode": {"target_duration_minutes": 25}, "schedule": {"drop_time": "05:00"},
              "voices": {"AVA": "en-US-AriaNeural", "ANDREW": "en-US-GuyNeural"},
              "spotify": {"show_id": "spotify:show:abc", "show_name": "Andrew's Rundown"}}
    form = yaml_to_form(profile, config)
    assert form["show_id"] == "spotify:show:abc"
    assert form["show_name"] == "Andrew's Rundown"
    assert form["name"] == "Andrew Sousa"
    # only weight==1.0 are headline focus (capped at 3); the rest are broader interests
    assert form["top"] == ["technology", "defense"]
    assert form["other"] == ["business", "science"]
    assert "lead_hours" not in form                # build buffer no longer in the form
    assert form["length"] == 25
    assert form["time"] == "05:00"
    assert form["voice"] == "aria_guy"            # matched the Aria+Guy pair
    assert form["tone"] == 40
    assert form["avoid"] == ["sports"] and form["must_cover"] == ["earnings"]


def test_yaml_to_form_migrates_legacy_favor_to_must_cover():
    form = yaml_to_form({"favor": ["earnings"]}, {})   # old dead key, no must_cover yet
    assert form["must_cover"] == ["earnings"]


def test_autofill_show_prefills_when_unset(monkeypatch):
    import briefing.web.app as app
    monkeypatch.setattr(app, "_spotify_shows",
                        lambda: [{"uri": "spotify:show:abc", "title": "My Show"}])
    out = app._autofill_show({"show_id": "", "show_name": ""})
    assert out["show_id"] == "spotify:show:abc" and out["show_name"] == "My Show"
    # never overrides an id the user already set, and won't clobber a custom name
    kept = app._autofill_show({"show_id": "spotify:show:keep", "show_name": "Mine"})
    assert kept["show_id"] == "spotify:show:keep" and kept["show_name"] == "Mine"


def test_autofill_show_noop_when_no_cli(monkeypatch):
    import briefing.web.app as app
    monkeypatch.setattr(app, "_spotify_shows", lambda: [])
    assert app._autofill_show({"show_id": "", "show_name": ""}) == {"show_id": "", "show_name": ""}


def test_autofill_show_treats_example_placeholder_as_unset(monkeypatch):
    import briefing.web.app as app
    monkeypatch.setattr(app, "_spotify_shows",
                        lambda: [{"uri": "spotify:show:real", "title": "Real"}])
    out = app._autofill_show({"show_id": "spotify:show:REPLACE_ME", "show_name": ""})
    assert out["show_id"] == "spotify:show:real"
    # and with no CLI shows, the placeholder is cleared rather than shown
    monkeypatch.setattr(app, "_spotify_shows", lambda: [])
    assert app._autofill_show({"show_id": "spotify:show:REPLACE_ME", "show_name": ""})["show_id"] == ""


def test_tone_slider_sets_tone_when_empty_or_preset():
    # empty tone -> slider writes the preset
    p, _ = form_to_yaml({"tone": 10}, {}, {})
    assert p["style"]["tone"] == TONE_PRESETS["ANALYTICAL"]
    # an existing preset -> slider may switch it to another preset
    p2, _ = form_to_yaml({"tone": 90}, {"style": {"tone": TONE_PRESETS["ANALYTICAL"]}}, {})
    assert p2["style"]["tone"] == TONE_PRESETS["PLAYFUL"]


def test_custom_feeds_round_trip_and_skip_builtins():
    from briefing.web.app import BUILTIN_IDS
    builtin = next(iter(BUILTIN_IDS))                  # any shipped feed id
    config = {"sources": [
        {"id": builtin, "name": "shadow", "type": "rss", "url": "x", "topics": ["world"]},
        {"id": "wbur", "name": "WBUR", "type": "rss", "url": "https://wbur/rss", "topics": ["local"]},
    ]}
    form = yaml_to_form({}, config)
    assert form["sources"] == [{"name": "WBUR", "url": "https://wbur/rss", "topic": "local"}]

    _, new_config = form_to_yaml(
        {"sources": [{"name": "My Town Times", "url": "https://mtt/feed", "topic": "local"}]}, {}, config)
    assert new_config["sources"] == [
        {"id": "my_town_times", "name": "My Town Times", "type": "rss",
         "url": "https://mtt/feed", "topics": ["local"]}]


def test_form_to_yaml_preserves_untouched_keys():
    profile = {
        "owner": {"name": "Old", "location": {"city": "Natick"}},
        "interests": [{"topic": "defense", "weight": 0.9, "keywords": ["DoD"]}],
        "style": {"tone": "the rich Marketplace paragraph", "inspirations": ["Marketplace"]},
        "avoid": ["old"], "favor": ["stale"],
    }
    config = {"sources": [{"id": "wbur"}], "weather": {"latitude": 42.0},
              "llm": {"default_model": "claude-opus-4-8"}, "episode": {"target_duration_minutes": 25}}
    form = {"name": "Andrew", "top": ["defense"], "other": ["ai startups"],
            "length": 20, "time": "08:00", "voice": "jenny_brian", "tone": 70,
            "show_id": "spotify:show:xyz", "show_name": "Andrew's Rundown",
            "must_cover": ["earnings"], "avoid": ["celebrity"]}

    new_profile, new_config = form_to_yaml(form, profile, config)

    # patched
    assert new_profile["owner"]["name"] == "Andrew"
    assert new_config["episode"]["target_duration_minutes"] == 20
    assert new_config["voices"]["AVA"] == "en-US-JennyNeural"     # the pair sets both
    assert new_config["voices"]["ANDREW"] == "en-US-BrianNeural"
    assert new_config["schedule"]["drop_time"] == "08:00"
    assert new_config["schedule"]["lead_hours"] == 2             # fixed build buffer kept
    assert new_config["spotify"]["show_id"] == "spotify:show:xyz"
    assert new_config["spotify"]["show_name"] == "Andrew's Rundown"
    assert new_profile["avoid"] == ["celebrity"]
    # must_cover is written; the legacy `favor` key is dropped
    assert new_profile["must_cover"] == ["earnings"]
    assert "favor" not in new_profile
    # top -> weight 1.0 (keeps existing keywords), other -> 0.5, freeform self-keywords
    by_topic = {i["topic"]: i for i in new_profile["interests"]}
    assert by_topic["defense"]["weight"] == 1.0 and by_topic["defense"]["keywords"] == ["DoD"]
    assert by_topic["ai startups"]["weight"] == 0.5
    assert by_topic["ai startups"]["keywords"] == ["ai startups"]
    # slider tracks the label/position, but a hand-written tone sentence is preserved
    assert new_profile["style"]["playfulness"] == 70
    assert new_profile["style"]["tone_label"] == "PLAYFUL"
    assert new_profile["style"]["tone"] == "the rich Marketplace paragraph"
    assert new_profile["style"]["inspirations"] == ["Marketplace"]   # unknown style keys preserved
    # untouched operational keys preserved
    assert new_config["sources"] == [{"id": "wbur"}]
    assert new_config["weather"] == {"latitude": 42.0}
    assert new_config["llm"] == {"default_model": "claude-opus-4-8"}
    assert new_profile["owner"]["location"] == {"city": "Natick"}
