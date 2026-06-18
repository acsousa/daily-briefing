"""Config loader: example base + personal overrides, with sources appended."""
import briefing.config as config


def _write(dir, name, text):
    (dir / name).write_text(text)


def test_personal_overrides_and_sources_append(tmp_path, monkeypatch):
    _write(tmp_path, "config.example.yaml", """
spotify: {show_id: "spotify:show:EXAMPLE"}
voices: {ARIA: a, ANDREW: b}
sources:
  - {id: s1, name: One, type: rss, url: u1, topics: [technology]}
  - {id: s2, name: Two, type: rss, url: u2, topics: [world]}
""")
    _write(tmp_path, "config.yaml", """
spotify: {show_id: "spotify:show:PERSONAL"}
sources:
  - {id: local1, name: Local, type: rss, url: u3, topics: [local]}
""")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)

    cfg = config.load_config()
    assert cfg["spotify"]["show_id"] == "spotify:show:PERSONAL"   # personal overrides
    assert cfg["voices"] == {"ARIA": "a", "ANDREW": "b"}          # inherited from example
    assert {s["id"] for s in cfg["sources"]} == {"s1", "s2", "local1"}   # appended


def test_falls_back_to_example_when_no_personal(tmp_path, monkeypatch):
    _write(tmp_path, "config.example.yaml", "spotify: {show_id: EX}\nsources: []\n")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    assert config.load_config()["spotify"]["show_id"] == "EX"


def test_personal_source_overrides_by_id(tmp_path, monkeypatch):
    _write(tmp_path, "config.example.yaml", """
sources:
  - {id: s1, name: Old, type: rss, url: old, topics: [technology]}
""")
    _write(tmp_path, "config.yaml", """
sources:
  - {id: s1, name: New, type: rss, url: new, topics: [technology]}
""")
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path)
    sources = config.load_config()["sources"]
    assert len(sources) == 1 and sources[0]["name"] == "New"
