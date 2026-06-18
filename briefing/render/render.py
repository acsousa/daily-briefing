#!/usr/bin/env python3
"""
Render a two-host briefing script to a single dated MP3.

Input format (briefings/briefing.txt): one line per turn, prefixed with a speaker
tag (ARIA: / ANDREW:). Lines without a tag continue the previous speaker. Each turn
is rendered with edge-tts in its host's voice at a slightly faster tempo, short
silence is inserted between turns, and everything is concatenated with ffmpeg into
briefings/briefing-YYYY-MM-DD.mp3.

edge-tts and ffmpeg are invoked as subprocesses (not imported), so this module runs
under the system Python as well as the project venv.
"""
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# ---- config -----------------------------------------------------------------
VOICES = {
    "ARIA": "en-US-AriaNeural",
    "ANDREW": "en-US-AndrewNeural",
}
RATE = "+12%"          # slightly faster tempo than default
GAP_SECONDS = 0.35     # silence between turns
SCRIPT_FILE = "briefing.txt"
# -----------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]   # briefing/render/render.py -> repo root
BRIEFINGS_DIR = REPO_ROOT / "briefings"            # script input + rendered MP3 outputs


def parse_turns(text):
    turns = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        spk = None
        for tag in VOICES:
            if line.upper().startswith(tag + ":"):
                spk = tag
                content = line[len(tag) + 1:].strip()
                break
        if spk:
            turns.append([spk, content])
        elif turns:                      # continuation of previous speaker
            turns[-1][1] += " " + line
        else:
            raise SystemExit(f"First non-blank line must start with a speaker tag {list(VOICES)}: {line!r}")
    return turns


def run(cmd):
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return res


def main():
    script_path = BRIEFINGS_DIR / SCRIPT_FILE
    turns = parse_turns(script_path.read_text())
    if not turns:
        raise SystemExit("no turns parsed from script")

    out = BRIEFINGS_DIR / f"briefing-{date.today().isoformat()}.mp3"

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        # one shared silence clip reused between every turn
        silence = td / "silence.mp3"
        run(["ffmpeg", "-y", "-f", "lavfi", "-i",
             "anullsrc=channel_layout=mono:sample_rate=24000",
             "-t", str(GAP_SECONDS), "-q:a", "9", str(silence)])

        concat_list = []
        for i, (spk, content) in enumerate(turns):
            seg = td / f"seg_{i:03d}.mp3"
            run(["edge-tts", "--voice", VOICES[spk], "--rate", RATE,
                 "--text", content, "--write-media", str(seg)])
            concat_list.append(seg)
            if i != len(turns) - 1:
                concat_list.append(silence)
            print(f"  [{spk:6}] {content[:60]}{'…' if len(content) > 60 else ''}")

        listfile = td / "concat.txt"
        listfile.write_text("".join(f"file '{p}'\n" for p in concat_list))
        run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
             "-c", "copy", str(out)])

    print(f"\nWrote {out}")
    return out


if __name__ == "__main__":
    main()
