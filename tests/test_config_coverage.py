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
