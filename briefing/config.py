"""Load personal + operational config.

The committed `*.example.yaml` is the base (generic defaults + the broad shared
source catalog). The gitignored personal `*.yaml` layers on top:
- top-level keys in the personal file override the example;
- `sources` is the exception — personal sources are *appended* to the example
  catalog (deduped by id), so a user inherits the shared feeds and only adds their
  own (e.g. local) ones.

If no personal file exists, the example is used as-is, so a fresh clone runs.
"""
from pathlib import Path

import yaml

from .paths import REPO_ROOT   # re-exported for callers that import it from config


def _read(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {} if path.exists() else {}


def _merge_sources(base: list, personal: list) -> list:
    by_id = {s["id"]: s for s in base}
    for s in personal:                      # personal can add new or override by id
        by_id[s["id"]] = s
    return list(by_id.values())


def _load(name: str) -> dict:
    example = _read(REPO_ROOT / f"{name}.example.yaml")
    personal = _read(REPO_ROOT / f"{name}.yaml")
    if not example and not personal:
        raise FileNotFoundError(f"missing {name}.yaml and {name}.example.yaml in {REPO_ROOT}")
    merged = {**example, **personal}
    if "sources" in example or "sources" in personal:
        merged["sources"] = _merge_sources(example.get("sources") or [], personal.get("sources") or [])
    return merged


def load_config() -> dict:
    """Operational config (sources, weather, voices, show id, render settings)."""
    return _load("config")


def load_profile() -> dict:
    """Personal config (interests, style, host personas)."""
    return _load("profile")
