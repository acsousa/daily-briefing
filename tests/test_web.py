"""SIGNAL config-page mapping: form <-> YAML, patch-preserving."""
from briefing.web.app import form_to_yaml, yaml_to_form


def test_yaml_to_form_projects_values():
    profile = {
        "owner": {"name": "Andrew Sousa"},
        "interests": [{"topic": "technology", "weight": 1.0}, {"topic": "defense", "weight": 0.9}],
        "avoid": ["sports"], "favor": ["earnings"],
        "style": {"playfulness": 40, "tone": "rich paragraph"},
    }
    config = {"episode": {"target_duration_minutes": 25}, "schedule": {"drop_time": "05:00"},
              "voices": {"AVA": "en-US-AriaNeural", "ANDREW": "en-US-GuyNeural"}}
    form = yaml_to_form(profile, config)
    assert form["name"] == "Andrew Sousa"
    assert form["topics"] == ["technology", "defense"]
    assert form["length"] == 25
    assert form["time"] == "05:00"
    assert form["voice"] == "aria_guy"            # matched the Aria+Guy pair
    assert form["tone"] == 40
    assert form["avoid"] == ["sports"] and form["favor"] == ["earnings"]


def test_form_to_yaml_preserves_untouched_keys():
    profile = {
        "owner": {"name": "Old", "location": {"city": "Natick"}},
        "interests": [{"topic": "defense", "weight": 0.9, "keywords": ["DoD"]}],
        "style": {"tone": "the rich Marketplace paragraph", "inspirations": ["Marketplace"]},
        "avoid": ["old"],
    }
    config = {"sources": [{"id": "wbur"}], "weather": {"latitude": 42.0},
              "llm": {"default_model": "claude-opus-4-8"}, "episode": {"target_duration_minutes": 25}}
    form = {"name": "Andrew", "topics": ["defense", "ai startups"], "length": 20,
            "time": "08:00", "voice": "jenny_brian", "tone": 70,
            "favor": ["earnings"], "avoid": ["celebrity"]}

    new_profile, new_config = form_to_yaml(form, profile, config)

    # patched
    assert new_profile["owner"]["name"] == "Andrew"
    assert new_config["episode"]["target_duration_minutes"] == 20
    assert new_config["voices"]["AVA"] == "en-US-JennyNeural"     # the pair sets both
    assert new_config["voices"]["ANDREW"] == "en-US-BrianNeural"
    assert new_config["schedule"]["drop_time"] == "08:00"
    assert new_profile["avoid"] == ["celebrity"] and new_profile["favor"] == ["earnings"]
    # existing 'defense' interest keeps its weight/keywords; freeform topic gets a keyword
    by_topic = {i["topic"]: i for i in new_profile["interests"]}
    assert by_topic["defense"]["weight"] == 0.9 and by_topic["defense"]["keywords"] == ["DoD"]
    assert by_topic["ai startups"]["keywords"] == ["ai startups"]
    # tone slider sets playfulness/label but does NOT clobber the rich tone paragraph
    assert new_profile["style"]["playfulness"] == 70
    assert new_profile["style"]["tone_label"] == "PLAYFUL"
    assert new_profile["style"]["tone"] == "the rich Marketplace paragraph"
    assert new_profile["style"]["inspirations"] == ["Marketplace"]
    # untouched operational keys preserved
    assert new_config["sources"] == [{"id": "wbur"}]
    assert new_config["weather"] == {"latitude": 42.0}
    assert new_config["llm"] == {"default_model": "claude-opus-4-8"}
    assert new_profile["owner"]["location"] == {"city": "Natick"}
