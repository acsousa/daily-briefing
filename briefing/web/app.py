"""SIGNAL config page — a local web UI that reads and writes profile.yaml / config.yaml.

A dependency-free stdlib HTTP server serves a single static page (the SIGNAL design) and
exposes a tiny JSON API. Saving PATCHES the personal YAML files (preserving sources, llm,
weather, etc.) rather than replacing them. Launch with `brief config`.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import yaml

from ..config import REPO_ROOT

STATIC = Path(__file__).resolve().parent / "static"

# Canonical topic taxonomy (matches how sources are tagged) — the suggested chips.
TAXONOMY = ["technology", "defense", "robotics", "business", "science", "health",
            "world", "politics", "sports", "entertainment", "local"]

# Region-of-focus suggestions (multi-select). Default is U.S.
REGIONS = ["U.S.", "Europe", "Canada", "South America", "Asia"]

# Interests come in two tiers the form presents simply: a few headline themes that set
# the tone (TOP_WEIGHT), and a broader set that's also covered (OTHER_WEIGHT).
TOP_WEIGHT, OTHER_WEIGHT, MAX_TOP = 1.0, 0.5, 3


def _geocode(place: str):
    """Open-Meteo geocoding (no key) -> (lat, lon, city, state) or None."""
    if not place.strip():
        return None
    try:
        q = urllib.parse.urlencode({"name": place.split(",")[0].strip(), "count": 1})
        with urllib.request.urlopen(
                f"https://geocoding-api.open-meteo.com/v1/search?{q}", timeout=8) as r:
            res = (json.loads(r.read()).get("results") or [None])[0]
        if res:
            return res["latitude"], res["longitude"], res.get("name", ""), res.get("admin1", "")
    except Exception:
        return None
    return None

# Dual-host voice pairs (female anchor + male analyst) behind the design's voice cards.
# `ava`/`andrew` are the edge-tts voices for the AVA-role and ANDREW-role script tags.
VOICE_OPTIONS = [
    {"id": "ava_andrew", "name": "AVA & ANDREW", "desc": "Ava ♀ expressive · Andrew ♂ warm",
     "ava": "en-US-AvaNeural", "andrew": "en-US-AndrewNeural"},
    {"id": "aria_guy", "name": "ARIA & GUY", "desc": "Aria ♀ crisp · Guy ♂ easy",
     "ava": "en-US-AriaNeural", "andrew": "en-US-GuyNeural"},
    {"id": "jenny_brian", "name": "JENNY & BRIAN", "desc": "Jenny ♀ warm · Brian ♂ mellow",
     "ava": "en-US-JennyNeural", "andrew": "en-US-BrianNeural"},
    {"id": "emma_eric", "name": "EMMA & ERIC", "desc": "Emma ♀ bright · Eric ♂ calm",
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


# The tone slider maps to the free-text `style.tone` that the scriptwriter + editor
# actually read (script.py / editor.py). Without this the slider set only a label and
# changed nothing in the output.
TONE_PRESETS = {
    "ANALYTICAL": "Analytical and precise. Lead with the facts and their implications; "
                  "minimal banter. Substance over color.",
    "BALANCED": "Smart, concise, conversational. Substance over hype, with a light human touch.",
    "PLAYFUL": "Warm, lively, and a little playful. Banter and color are welcome — "
               "but never at the expense of accuracy.",
}


def _os_label() -> str:
    """Friendly name for the auto-detected host OS (shown in the page header)."""
    return {"Darwin": "macOS", "Linux": "Linux", "Windows": "Windows"}.get(
        platform.system(), platform.system() or "unknown")


# Model-quality presets (friendly stand-in for the three llm.* model fields).
QUALITY = {
    "opus":   {"default_model": "claude-opus-4-8", "editor_model": "claude-opus-4-8", "script_model": "claude-opus-4-8"},
    "sonnet": {"default_model": "claude-sonnet-4-6", "editor_model": "claude-sonnet-4-6", "script_model": "claude-sonnet-4-6"},
    "mixed":  {"default_model": "claude-sonnet-4-6", "editor_model": "claude-opus-4-8", "script_model": "claude-sonnet-4-6"},
}
QUALITY_OPTIONS = [
    {"id": "opus", "name": "Highest quality", "desc": "Opus everywhere"},
    {"id": "mixed", "name": "Balanced", "desc": "Opus editor · Sonnet copy"},
    {"id": "sonnet", "name": "Economy", "desc": "Sonnet everywhere"},
]


def _quality_of(llm: dict) -> str:
    models = {llm.get("default_model"), llm.get("editor_model"), llm.get("script_model")}
    if models == {"claude-opus-4-8"}:
        return "opus"
    if models == {"claude-sonnet-4-6"}:
        return "sonnet"
    return "mixed"


def _raw_text(name: str) -> str:
    personal = REPO_ROOT / f"{name}.yaml"
    example = REPO_ROOT / f"{name}.example.yaml"
    src = personal if personal.exists() else example
    return src.read_text() if src.exists() else ""


def _location_str(owner: dict) -> str:
    loc = owner.get("location") or {}
    parts = [loc.get("city", ""), loc.get("state", "")]
    return ", ".join(p for p in parts if p)


def _builtin_sources() -> list[dict]:
    """The shipped feed catalog (config.example.yaml). These merge in via load_config,
    so the form treats them as read-only built-ins and only manages the user's own feeds."""
    ex = REPO_ROOT / "config.example.yaml"
    data = (yaml.safe_load(ex.read_text()) or {}) if ex.exists() else {}
    return data.get("sources") or []


BUILTIN_IDS = {s.get("id") for s in _builtin_sources()}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_") or "feed"


def _save_to_spotify_bin() -> str:
    """Resolve the save-to-spotify CLI (PATH, then the usual install dirs)."""
    found = shutil.which("save-to-spotify")
    if found:
        return found
    for p in (Path.home() / ".local/bin/save-to-spotify", Path("/usr/local/bin/save-to-spotify")):
        if p.exists():
            return str(p)
    return ""


def _spotify_shows() -> list[dict]:
    """Best-effort list of Spotify shows for the authed account (CLI-created). [] on any error."""
    sts = _save_to_spotify_bin()
    if not sts:
        return []
    try:
        r = subprocess.run([sts, "--json", "shows"], capture_output=True, text=True, timeout=15)
        data = json.loads(r.stdout or "{}")
        return [{"uri": s.get("show_uri", ""), "title": s.get("title", "")}
                for s in (data.get("shows") or []) if s.get("show_uri")]
    except Exception:
        return []


def _autofill_show(form: dict) -> dict:
    """If the config has no real show id (unset, or the example's REPLACE_ME placeholder),
    pre-fill it (and the show name) from a Spotify show the save-to-spotify CLI can see.
    Never overrides an id the user already set."""
    current = (form.get("show_id") or "").strip()
    if current and "REPLACE" not in current:
        return form
    form["show_id"] = ""                              # drop the example placeholder
    shows = _spotify_shows()
    if shows:
        form["show_id"] = shows[0]["uri"]
        if not form.get("show_name"):
            form["show_name"] = shows[0]["title"]
    return form


def _interest_tiers(profile: dict) -> dict:
    """Bucket interests into headline focus (highest-weighted, up to MAX_TOP) and the rest.
    Legacy profiles with assorted weights still bucket sensibly; the form re-normalizes
    everything to TOP_WEIGHT / OTHER_WEIGHT on save."""
    interests = [i for i in (profile.get("interests") or []) if isinstance(i, dict) and "topic" in i]
    top, other = [], []
    for i in sorted(interests, key=lambda x: -float(x.get("weight", 0))):
        if float(i.get("weight", 0)) >= TOP_WEIGHT and len(top) < MAX_TOP:
            top.append(i["topic"])
        else:
            other.append(i["topic"])
    return {"top": top, "other": other}


def yaml_to_form(profile: dict, config: dict) -> dict:
    """Project the current YAML into the form's value shape (for prefill)."""
    style = profile.get("style") or {}
    owner = profile.get("owner") or {}
    return {
        "name": owner.get("name", ""),
        "location": _location_str(owner),
        "regions": list(profile.get("regions") or ["U.S."]),
        **_interest_tiers(profile),                  # -> {"top": [...], "other": [...]}
        "length": int((config.get("episode") or {}).get("target_duration_minutes", 10)),
        "time": (config.get("schedule") or {}).get("drop_time", "08:00"),
        "quality": _quality_of(config.get("llm") or {}),
        "voice": _pair_for(config.get("voices") or {}),
        "show_id": (config.get("spotify") or {}).get("show_id", ""),
        "show_name": (config.get("spotify") or {}).get("show_name", ""),
        "sources": [{"name": s.get("name", ""), "url": s.get("url", ""),
                     "topic": (s.get("topics") or [""])[0]}
                    for s in (config.get("sources") or []) if s.get("id") not in BUILTIN_IDS],
        "tone": int(style.get("playfulness", 35)),
        "must_cover": list(profile.get("must_cover") or profile.get("favor") or []),
        "avoid": list(profile.get("avoid", [])),
    }


def form_to_yaml(form: dict, profile: dict, config: dict) -> tuple[dict, dict]:
    """Patch the form's values onto existing YAML, preserving everything else."""
    profile = dict(profile or {})
    config = dict(config or {})

    owner = dict(profile.get("owner") or {})
    owner["name"] = (form.get("name") or "").strip()
    location = (form.get("location") or "").strip()
    if location:
        geo = _geocode(location)
        if geo:
            lat, lon, city, admin = geo
            owner["location"] = {"city": city or location, "state": admin,
                                 "timezone": (owner.get("location") or {}).get("timezone", "America/New_York")}
            weather = dict(config.get("weather") or {})
            weather["latitude"] = round(lat, 4)
            weather["longitude"] = round(lon, 4)
            config["weather"] = weather
        else:                                    # keep coords; record the text the user gave
            loc = dict(owner.get("location") or {})
            loc["city"] = location.split(",")[0].strip()
            owner["location"] = loc
    profile["owner"] = owner
    profile["regions"] = list(form.get("regions") or ["U.S."])

    # Two tiers from the form -> interests. Keywords aren't edited here; preserve any the
    # profile already has (the pipeline auto-matches on topic when there are none).
    existing_kw = {i.get("topic"): list(i.get("keywords") or [])
                   for i in (profile.get("interests") or []) if isinstance(i, dict)}
    interests, seen = [], set()

    def _add(topic, weight):
        topic = (topic or "").strip()
        if not topic or topic in seen:
            return
        seen.add(topic)
        kws = existing_kw.get(topic, [])
        if not kws and topic not in TAXONOMY:       # freeform topic keeps itself as a keyword seed
            kws = [topic]
        interests.append({"topic": topic, "weight": weight, "keywords": kws})

    for topic in (form.get("top") or [])[:MAX_TOP]:
        _add(topic, TOP_WEIGHT)
    for topic in (form.get("other") or []):
        _add(topic, OTHER_WEIGHT)
    profile["interests"] = interests
    profile["avoid"] = list(form.get("avoid", []))
    profile["must_cover"] = list(form.get("must_cover", []))
    profile.pop("favor", None)                      # migrate the old (dead) key away

    style = dict(profile.get("style") or {})
    tone = int(form.get("tone", 35))
    label = _tone_label(tone)
    style["playfulness"] = tone                     # remembers the slider position for round-trip
    style["tone_label"] = label
    # The slider sets the tone sentence the scriptwriter/editor read — but never clobbers a
    # hand-written one. A custom style.tone (not one of our presets) is preserved as-is.
    current = (style.get("tone") or "").strip()
    if not current or current in TONE_PRESETS.values():
        style["tone"] = TONE_PRESETS[label]
    profile["style"] = style

    episode = dict(config.get("episode") or {})
    episode["target_duration_minutes"] = int(form.get("length", 10))
    config["episode"] = episode

    schedule = dict(config.get("schedule") or {})
    schedule["drop_time"] = form.get("time", "08:00")
    schedule.setdefault("lead_hours", 2)            # build buffer is fixed; not exposed in the form
    config["schedule"] = schedule

    quality = form.get("quality")
    if quality in QUALITY:
        llm = dict(config.get("llm") or {})
        llm.update(QUALITY[quality])
        config["llm"] = llm

    pair = _pair_by_id(form.get("voice") or _DEFAULT_PAIR["id"])
    voices = dict(config.get("voices") or {})
    voices["AVA"] = pair["ava"]
    voices["ANDREW"] = pair["andrew"]
    config["voices"] = voices

    if "show_id" in form or "show_name" in form:    # Spotify show to publish to (optional)
        spotify = dict(config.get("spotify") or {})
        if "show_id" in form:
            spotify["show_id"] = (form.get("show_id") or "").strip()
        if "show_name" in form:
            spotify["show_name"] = (form.get("show_name") or "").strip()
        config["spotify"] = spotify

    if "sources" in form:                           # user's own feeds (built-ins come from example)
        custom, seen = [], set()
        for s in form.get("sources") or []:
            name, url = (s.get("name") or "").strip(), (s.get("url") or "").strip()
            if not name or not url:
                continue
            sid = _slug(name)
            while sid in seen or sid in BUILTIN_IDS:
                sid += "_"
            seen.add(sid)
            topic = (s.get("topic") or "").strip()
            custom.append({"id": sid, "name": name, "type": "rss", "url": url,
                           "topics": [topic] if topic else []})
        config["sources"] = custom

    return profile, config


def save_form(form: dict) -> None:
    profile, config = form_to_yaml(form, _read_yaml("profile"), _read_yaml("config"))
    _write_yaml("profile", profile)
    _write_yaml("config", config)


# --- config-page coverage map -------------------------------------------------
# Every leaf key in profile.example.yaml + config.example.yaml must appear here,
# either as a field the friendly form edits (FORM_FIELDS) or one intentionally
# left to the raw-YAML editor (RAW_ONLY). tests/test_config_coverage.py enforces
# this so the page and the YAML can never silently drift apart again — add a new
# config field and the test fails until you surface it (form) or list it (raw).
FORM_FIELDS = {
    "owner.name", "owner.location.city", "owner.location.state",
    "interests", "regions", "must_cover", "avoid", "style.tone",
    "sources", "weather.latitude", "weather.longitude",
    "spotify.show_id", "spotify.show_name",
    "episode.target_duration_minutes", "schedule.drop_time",
    "llm.default_model", "llm.editor_model", "llm.script_model",
    "voices.AVA", "voices.ANDREW",
}
RAW_ONLY = {
    "owner.location.timezone", "limits.max_segments",
    "schedule.lead_hours",                          # fixed build buffer, not exposed in the form
    "ingest.window_hours", "weather.provider",
    "continuity.recent_days", "continuity.week_days", "continuity.month_days",
    "ranking.weights.freshness", "ranking.weights.importance", "ranking.weights.interest",
    "ranking.weights.region", "ranking.weights.novelty",
    "render.rate", "render.gap_seconds", "render.segment_gap_seconds",
    "render.music.enabled", "render.music.dir", "render.music.min_seconds",
    "render.music.max_seconds", "render.music.intro_seconds",
    "render.intro", "render.sting",
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store, must-revalidate")  # always serve fresh
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/config":
            form = _autofill_show(yaml_to_form(_read_yaml("profile"), _read_yaml("config")))
            self._send(200, json.dumps(form))
        elif self.path == "/api/meta":
            from ..schedule import mechanism
            builtin = [{"name": s.get("name", s.get("id", "")), "topics": s.get("topics", [])}
                       for s in _builtin_sources()]
            self._send(200, json.dumps({"suggested": TAXONOMY, "voices": VOICE_OPTIONS,
                                        "regions": REGIONS, "quality": QUALITY_OPTIONS,
                                        "taxonomy": TAXONOMY, "builtin_sources": builtin,
                                        "scheduler": mechanism(), "os": _os_label()}))
        elif self.path == "/api/raw":                # full files, for the advanced editor
            self._send(200, json.dumps({"profile": _raw_text("profile"),
                                        "config": _raw_text("config")}))
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(n) or b"{}"
        try:
            if self.path == "/api/config":
                save_form(json.loads(body))
            elif self.path == "/api/raw":
                payload = json.loads(body)
                for name in ("profile", "config"):
                    text = payload.get(name)
                    if text is not None:
                        yaml.safe_load(text)         # validate it parses before writing
                        (REPO_ROOT / f"{name}.yaml").write_text(text)
            else:
                return self._send(404, '{"error":"not found"}')
            self._send(200, '{"ok":true}')
        except Exception as exc:                     # surface, don't crash the server
            self._send(400, json.dumps({"error": str(exc)}))

    def log_message(self, *a):                       # quiet
        pass


def serve(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    httpd = HTTPServer((host, port), Handler)
    shown = "127.0.0.1" if host in ("127.0.0.1", "0.0.0.0") else host
    url = f"http://{shown}:{port}/"
    print(f"SIGNAL config → {url}   (Ctrl-C to stop)")
    # Skip the browser on a headless box (Linux server with no display) — print only.
    headless = platform.system() == "Linux" and not os.environ.get("DISPLAY")
    if open_browser and not headless:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    elif headless:
        print("  (headless: open the URL yourself, or SSH-tunnel "
              f"`ssh -L {port}:127.0.0.1:{port} ...`)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
        httpd.server_close()
