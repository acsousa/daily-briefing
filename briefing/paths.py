"""Single source of truth for the repository root.

Imported everywhere instead of each module computing its own `parents[N]` — so moving a
file can't silently point .env / briefings/ at the wrong place.
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]   # briefing/ -> repo root
