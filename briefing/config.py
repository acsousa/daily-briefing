"""Load personal + operational config.

Prefers the personal file (config.yaml / profile.yaml) and falls back to the
committed generic example, so a fresh clone runs out of the box.
"""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str) -> dict:
    personal = REPO_ROOT / f"{name}.yaml"
    example = REPO_ROOT / f"{name}.example.yaml"
    path = personal if personal.exists() else example
    if not path.exists():
        raise FileNotFoundError(f"missing {name}.yaml and {name}.example.yaml in {REPO_ROOT}")
    return yaml.safe_load(path.read_text()) or {}


def load_config() -> dict:
    """Operational config (sources, weather, voices, show id, render settings)."""
    return _load("config")


def load_profile() -> dict:
    """Personal config (interests, style, host personas)."""
    return _load("profile")
