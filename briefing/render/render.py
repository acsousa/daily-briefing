#!/usr/bin/env python3
"""
Render a two-host briefing script to a single dated MP3.

Input (briefings/briefing.txt): one line per turn, prefixed with a speaker tag
(AVA: / ANDREW:). Lines without a tag continue the previous speaker. A `[[SEG]]` marker
line is a segment boundary — the renderer inserts a longer pause and a short music sting
there (blank lines are cosmetic and ignored).

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

DEFAULT_VOICES = {"AVA": "en-US-AvaNeural", "ANDREW": "en-US-AndrewNeural"}
SCRIPT_FILE = "briefing.txt"
SEG_MARKER = "[[SEG]]"          # segment boundary (longer pause + sting)

# Short musical motifs (note frequencies, Hz) rotated across segment boundaries — varied
# so the bumper doesn't get repetitive. Rendered as soft, mallet-like decaying tones.
STING_MOTIFS = [
    [523.25, 659.25, 783.99],   # C E G  — warm rise
    [440.00, 659.25],           # A E    — open fifth
    [587.33, 493.88, 392.00],   # D B G  — mellow fall
    [392.00, 523.25, 659.25],   # G C E  — bright rise
    [659.25, 587.33, 880.00],   # E D A  — lift
]

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIEFINGS_DIR = REPO_ROOT / "briefings"


def _config():
    try:
        from ..config import load_config
        cfg = load_config()
        return cfg.get("voices") or DEFAULT_VOICES, cfg.get("render") or {}
    except Exception:
        return DEFAULT_VOICES, {}


VOICES, _RENDER = _config()
RATE = _RENDER.get("rate", "+0%")
TURN_GAP = float(_RENDER.get("gap_seconds", 0.40))
SEGMENT_GAP = float(_RENDER.get("segment_gap_seconds", 0.7))
STING = _RENDER.get("sting", "generated")      # path to an audio file, "generated", or "none"
INTRO = _RENDER.get("intro", "generated")      # intro bumper before content: path/"generated"/"none"
ASSETS = REPO_ROOT / "briefings" / "assets"


def parse_turns(text):
    turns, seg_break = [], False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue                          # blank lines are cosmetic; ignore
        if line == SEG_MARKER:
            seg_break = True
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


def _tone_input(freq):
    # mallet-like tone: fundamental + softer octave, both exponentially decaying
    return (f"aevalsrc=0.6*sin(2*PI*{freq}*t)*exp(-3.5*t)"
            f"+0.25*sin(2*PI*{2 * freq}*t)*exp(-5*t):d=0.45:s=24000")


def _make_sting(path, motif, td, key):
    """Soft, slightly reverbed arpeggio bumper from a note motif (~1.5-2s)."""
    notes = []
    for j, freq in enumerate(motif):
        n = td / f"note_{key}_{j}.mp3"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", _tone_input(freq), "-q:a", "9", str(n)])
        notes.append(n)
    lst = td / f"sting_{key}.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in notes))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-af", "aecho=0.8:0.7:90:0.35,volume=0.32,apad=pad_dur=0.5,"
                "aformat=channel_layouts=mono:sample_rates=24000",
         "-q:a", "9", str(path)])


def _resolve_asset(value, td, generated_name):
    """Resolve a config audio value: 'none' -> None, 'generated' -> synth, else a path.

    A path may be absolute or relative to briefings/assets/. Provided files are
    re-encoded to the mono/24k mp3 the concat step needs.
    """
    if not value or value == "none":
        return None
    if value == "generated":
        out = td / generated_name
        if generated_name == "intro.mp3":
            _make_intro(out, td)
        else:
            _make_sting(out, STING_MOTIFS[0], td, "x")
        return out
    src = Path(value)
    if not src.is_absolute():
        src = ASSETS / value
    if not src.exists():
        print(f"  ! audio asset not found: {src} — skipping")
        return None
    out = td / generated_name
    run(["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "24000", "-q:a", "9", str(out)])
    return out


def _make_intro(path, td):
    """Generated intro bumper (fuller, ~4s) used until a real track is supplied."""
    notes = []
    motif = [392.00, 523.25, 659.25, 783.99, 1046.50]   # G C E G C — rising
    for j, freq in enumerate(motif):
        n = td / f"intro_{j}.mp3"
        dur = 0.7 if j == len(motif) - 1 else 0.32
        run(["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"aevalsrc=0.5*sin(2*PI*{freq}*t)*exp(-2.2*t)+0.25*sin(2*PI*{2*freq}*t)*exp(-3.5*t)"
             f"+0.15*sin(2*PI*{freq/2}*t)*exp(-1.5*t):d={dur}:s=24000", "-q:a", "9", str(n)])
        notes.append(n)
    lst = td / "intro.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in notes))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
         "-af", "aecho=0.8:0.7:110:0.4,volume=0.4,apad=pad_dur=0.7,"
                "aformat=channel_layouts=mono:sample_rates=24000",
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

        stings = []                                  # rotated across boundaries
        if STING == "generated":
            for i, motif in enumerate(STING_MOTIFS):
                s = td / f"sting_{i}.mp3"
                _make_sting(s, motif, td, i)
                stings.append(s)
        elif STING and STING != "none":
            one = _resolve_asset(STING, td, "sting.mp3")  # a provided audio file
            if one:
                stings = [one]

        intro = _resolve_asset(INTRO, td, "intro.mp3")
        clips, boundary = [], 0
        if intro:                                    # intro bumper, then a beat, then content
            clips.extend([intro, seg_gap])
        for i, t in enumerate(turns):
            if i > 0:
                if t["seg_break"]:
                    clips.append(seg_gap)
                    if stings:
                        clips.append(stings[boundary % len(stings)])
                        boundary += 1
                    clips.append(turn_gap)
                else:
                    clips.append(turn_gap)
            seg = td / f"turn_{i:03d}.mp3"
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
