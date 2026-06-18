#!/usr/bin/env python3
"""
Render a two-host briefing script to a single dated MP3.

Input (briefings/briefing.txt): one line per turn, prefixed with a speaker tag
(ARIA: / ANDREW:). Lines without a tag continue the previous speaker. A BLANK LINE
marks a segment boundary — the renderer inserts a longer pause and (optionally) a
short music sting there.

Voices, speaking rate, gaps, and the sting are read from config (voices / render
sections), falling back to defaults if config can't be loaded — so this runs under the
project venv (config honored) or bare system Python (defaults).

edge-tts and ffmpeg are invoked as subprocesses (not imported).
"""
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

DEFAULT_VOICES = {"ARIA": "en-US-AriaNeural", "ANDREW": "en-US-AndrewNeural"}
SCRIPT_FILE = "briefing.txt"
SEG_MARKER = "[[SEG]]"          # segment boundary (longer pause + sting)

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIEFINGS_DIR = REPO_ROOT / "briefings"


def _config():
    """voices + render settings from config, with defaults if unavailable."""
    try:
        from ..config import load_config
        cfg = load_config()
        return cfg.get("voices") or DEFAULT_VOICES, cfg.get("render") or {}
    except Exception:
        return DEFAULT_VOICES, {}


VOICES, _RENDER = _config()
RATE = _RENDER.get("rate", "+0%")
TURN_GAP = float(_RENDER.get("gap_seconds", 0.40))
SEGMENT_GAP = float(_RENDER.get("segment_gap_seconds", 1.1))
STING = _RENDER.get("sting", "generated")


def parse_turns(text):
    turns, seg_break = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue                          # blank lines are cosmetic; ignore
        if line == SEG_MARKER:
            seg_break = True                  # next turn starts a new segment
            continue
        spk = None
        for tag in VOICES:
            if line.upper().startswith(tag + ":"):
                spk, content = tag, line[len(tag) + 1:].strip()
                break
        if spk:
            turns.append({"spk": spk, "text": content, "seg_break": seg_break})
            seg_break = False
        elif turns:
            turns[-1]["text"] += " " + line
        else:
            raise SystemExit(f"First non-blank line must start with a speaker tag {list(VOICES)}: {line!r}")
    return turns


def run(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return res


def _silence(path, seconds):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i",
         "anullsrc=channel_layout=mono:sample_rate=24000",
         "-t", str(seconds), "-q:a", "9", str(path)])


def _make_sting(path):
    """Short, soft 3-note arpeggio bumper (generated — royalty-free)."""
    run(["ffmpeg", "-y", "-filter_complex",
         "sine=f=587.33:d=0.16[a];sine=f=783.99:d=0.16[b];sine=f=987.77:d=0.34[c];"
         "[a][b][c]concat=n=3:v=0:a=1,afade=t=in:st=0:d=0.02,afade=t=out:st=0.5:d=0.16,"
         "volume=0.22,aformat=channel_layouts=mono:sample_rates=24000",
         "-q:a", "9", str(path)])


def main():
    turns = parse_turns((BRIEFINGS_DIR / SCRIPT_FILE).read_text())
    if not turns:
        raise SystemExit("no turns parsed from script")
    out = BRIEFINGS_DIR / f"briefing-{date.today().isoformat()}.mp3"

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        turn_gap = td / "turn_gap.mp3"
        seg_gap = td / "seg_gap.mp3"
        _silence(turn_gap, TURN_GAP)
        _silence(seg_gap, SEGMENT_GAP)
        sting = None
        if STING and STING != "none":
            sting = td / "sting.mp3"
            if STING == "generated":
                _make_sting(sting)
            else:                                    # treat as a path to an audio file
                sting = Path(STING)

        clips = []
        for i, t in enumerate(turns):
            if i > 0:
                if t["seg_break"]:
                    clips.append(seg_gap)
                    if sting:
                        clips.append(sting)
                    clips.append(turn_gap)
                else:
                    clips.append(turn_gap)
            seg = td / f"seg_{i:03d}.mp3"
            run(["edge-tts", "--voice", VOICES[t["spk"]], "--rate", RATE,
                 "--text", t["text"], "--write-media", str(seg)])
            clips.append(seg)
            print(f"  [{t['spk']:6}]{' *' if t['seg_break'] else '  '}{t['text'][:58]}")

        listfile = td / "concat.txt"
        listfile.write_text("".join(f"file '{p}'\n" for p in clips))
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-c", "copy", str(out)])

    print(f"\nWrote {out}")
    return out


if __name__ == "__main__":
    main()
