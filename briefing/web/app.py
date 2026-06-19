"""SIGNAL config page — a local web UI that reads and writes profile.yaml / config.yaml.

A dependency-free stdlib HTTP server serves a single static page (the SIGNAL design) and
exposes a tiny JSON API. Saving PATCHES the personal YAML files (preserving sources, llm,
weather, etc.) rather than replacing them. Launch with `brief config`.
"""
from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

from ..config import REPO_ROOT

STATIC = Path(__file__).resolve().parent / "static"

# Canonical topic taxonomy (matches how sources are tagged) — the suggested chips.
TAXONOMY = ["technology", "defense", "robotics", "business", "science", "health",
            "world", "politics", "sports", "entertainment", "local"]

# Dual-host voice pairs (female anchor + male analyst) behind the design's voice cards.
# `ava`/`andrew` are the edge-tts voices for the AVA-role and ANDREW-role script tags.
VOICE_OPTIONS = [
    {"id": "ava_andrew", "name": "AVA & ANDREW", "desc": "Expressive ♀ · Warm ♂",
     "ava": "en-US-AvaNeural", "andrew": "en-US-AndrewNeural"},
    {"id": "aria_guy", "name": "ARIA & GUY", "desc": "Crisp ♀ · Easy ♂",
     "ava": "en-US-AriaNeural", "andrew": "en-US-GuyNeural"},
    {"id": "jenny_brian", "name": "JENNY & BRIAN", "desc": "Warm ♀ · Mellow ♂",
     "ava": "en-US-JennyNeural", "andrew": "en-US-BrianNeural"},
    {"id": "emma_eric", "name": "EMMA & ERIC", "desc": "Bright ♀ · Calm ♂",
     "ava": "en-US-EmmaNeural", "andrew": "en-US-EricNeural"},
]
_DEFAULT_PAIR = VOICE_OPTIONS[0]


def _pair_for(voices: dict) -> str:
    ava, andrew = voices.get("AVA"), voices.get("ANDREW")
    for p in VOICE_OPTIONS:
        if p["ava"] == ava and p["andrew"] == andrew:
            return p["id"]
    return _DEFAULT_PAIR["id"]


def _pair_by_id(pid: str) -> dict:
    return next((p for p in VOICE_OPTIONS if p["id"] == pid), _DEFAULT_PAIR)


def _read_yaml(name: str) -> dict:
    """Read the personal file if present, else the committed example."""
    personal = REPO_ROOT / f"{name}.yaml"
    example = REPO_ROOT / f"{name}.example.yaml"
    src = personal if personal.exists() else example
    return (yaml.safe_load(src.read_text()) or {}) if src.exists() else {}


def _write_yaml(name: str, data: dict) -> None:
    (REPO_ROOT / f"{name}.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _tone_label(t: int) -> str:
    return "ANALYTICAL" if t < 33 else "BALANCED" if t < 66 else "PLAYFUL"


def yaml_to_form(profile: dict, config: dict) -> dict:
    """Project the current YAML into the form's value shape (for prefill)."""
    style = profile.get("style") or {}
    return {
        "name": (profile.get("owner") or {}).get("name", ""),
        "topics": [i["topic"] for i in profile.get("interests", []) if isinstance(i, dict) and "topic" in i],
        "length": int((config.get("episode") or {}).get("target_duration_minutes", 10)),
        "time": (config.get("schedule") or {}).get("drop_time", "08:00"),
        "voice": _pair_for(config.get("voices") or {}),
        "tone": int(style.get("playfulness", 35)),
        "favor": list(profile.get("favor", [])),
        "avoid": list(profile.get("avoid", [])),
    }


def form_to_yaml(form: dict, profile: dict, config: dict) -> tuple[dict, dict]:
    """Patch the form's values onto existing YAML, preserving everything else."""
    profile = dict(profile or {})
    config = dict(config or {})

    owner = dict(profile.get("owner") or {})
    owner["name"] = (form.get("name") or "").strip()
    profile["owner"] = owner

    existing = {i.get("topic"): i for i in profile.get("interests", []) if isinstance(i, dict)}
    interests = []
    for topic in form.get("topics", []):
        if topic in existing:                       # keep prior weight/keywords
            interests.append(existing[topic])
        else:
            interests.append({"topic": topic, "weight": 1.0,
                              "keywords": [] if topic in TAXONOMY else [topic]})
    profile["interests"] = interests
    profile["avoid"] = list(form.get("avoid", []))
    profile["favor"] = list(form.get("favor", []))

    style = dict(profile.get("style") or {})        # preserve the rich tone paragraph etc.
    tone = int(form.get("tone", 35))
    style["playfulness"] = tone
    style["tone_label"] = _tone_label(tone)
    profile["style"] = style

    episode = dict(config.get("episode") or {})
    episode["target_duration_minutes"] = int(form.get("length", 10))
    config["episode"] = episode

    schedule = dict(config.get("schedule") or {})
    schedule["drop_time"] = form.get("time", "08:00")
    config["schedule"] = schedule

    pair = _pair_by_id(form.get("voice") or _DEFAULT_PAIR["id"])
    voices = dict(config.get("voices") or {})
    voices["AVA"] = pair["ava"]
    voices["ANDREW"] = pair["andrew"]
    config["voices"] = voices

    return profile, config


def save_form(form: dict) -> None:
    profile, config = form_to_yaml(form, _read_yaml("profile"), _read_yaml("config"))
    _write_yaml("profile", profile)
    _write_yaml("config", config)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/config":
            self._send(200, json.dumps(yaml_to_form(_read_yaml("profile"), _read_yaml("config"))))
        elif self.path == "/api/meta":
            self._send(200, json.dumps({"suggested": TAXONOMY, "voices": VOICE_OPTIONS}))
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        if self.path != "/api/config":
            return self._send(404, '{"error":"not found"}')
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            form = json.loads(self.rfile.read(n) or b"{}")
            save_form(form)
            self._send(200, '{"ok":true}')
        except Exception as exc:                     # surface, don't crash the server
            self._send(400, json.dumps({"error": str(exc)}))

    def log_message(self, *a):                       # quiet
        pass


def serve(port: int = 8765, open_browser: bool = True) -> None:
    httpd = HTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"SIGNAL config → {url}   (Ctrl-C to stop)")
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        httpd.server_close()
