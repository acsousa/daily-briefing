#!/usr/bin/env python3
"""Thin shim kept so make_briefing.sh keeps working.
Render logic lives in briefing/render/render.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from briefing.render.render import main

if __name__ == "__main__":
    main()
