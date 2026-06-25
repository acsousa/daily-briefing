"""Anti-drift guard: every example-YAML field is either edited by the config form
or explicitly listed as raw-only. Fails when a new profile/config field is added
without surfacing it — the regression that let `weight`, tone, and favor drift."""
import yaml

import briefing.config as config
from briefing.web.app import FORM_FIELDS, RAW_ONLY


def _leaves(d, prefix=""):
    """Dotted leaf paths; lists (sources, interests, regions, …) are atomic."""
    if isinstance(d, dict):
        out = []
        for k, v in d.items():
            out += _leaves(v, f"{prefix}.{k}" if prefix else k)
        return out
    return [prefix]


def _example_paths():
    paths = set()
    for name in ("profile", "config"):
        data = yaml.safe_load((config.REPO_ROOT / f"{name}.example.yaml").read_text()) or {}
        paths |= set(_leaves(data))
    return paths


def test_every_example_field_is_classified():
    paths = _example_paths()
    classified = FORM_FIELDS | RAW_ONLY
    missing = paths - classified       # a YAML field nobody surfaced in the page or the allowlist
    stale = classified - paths         # a classified path that no longer exists in the example
    assert not missing, f"config fields not surfaced in the page or RAW_ONLY: {sorted(missing)}"
    assert not stale, f"classified fields missing from the example YAML: {sorted(stale)}"


def test_form_and_raw_are_disjoint():
    assert not (FORM_FIELDS & RAW_ONLY), sorted(FORM_FIELDS & RAW_ONLY)


def _dig(d, dotted):
    cur = d
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def test_form_save_preserves_raw_only_keys():
    """The definitive data-loss guard: a real example round-trip through the form
    (yaml_to_form -> form_to_yaml, as SAVE CONFIG does) must not drop any raw-only
    key — ranking weights, render/music, continuity, limits, etc."""
    from briefing.web.app import form_to_yaml, yaml_to_form
    profile = yaml.safe_load((config.REPO_ROOT / "profile.example.yaml").read_text()) or {}
    cfg = yaml.safe_load((config.REPO_ROOT / "config.example.yaml").read_text()) or {}
    new_profile, new_config = form_to_yaml(yaml_to_form(profile, cfg), profile, cfg)
    for path in RAW_ONLY:
        present_before = _dig(profile, path) or _dig(cfg, path)
        if not present_before:
            continue  # not shipped in the example; nothing to preserve
        assert _dig(new_profile, path) or _dig(new_config, path), \
            f"SAVE CONFIG dropped raw-only key: {path}"
