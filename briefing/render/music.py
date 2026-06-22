"""Music engine: cut good-sounding snippets from a folder of tracks and weave them
between news segments, rotating song/section choices day to day.

Snippet selection is deterministic per seed (the date) so a given day is reproducible but
days differ. The cut points avoid each track's intro/outro and land in its body, with
fades — a pragmatic stand-in for "the good part". Selection logic is separated from ffmpeg
so it's unit-testable.
"""
from __future__ import annotations

import random
import re
import subprocess
from pathlib import Path

AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".flac", ".ogg", ".aac"}
SKIP_INTRO = 12.0          # skip a track's opening when choosing a cut
SKIP_OUTRO = 8.0           # ...and its ending


def _dedupe_key(name: str) -> str:
    return re.sub(r"\s*\(\d+\)\s*$", "", Path(name).stem).strip().lower()


def list_tracks(music_dir: Path) -> list[Path]:
    if not music_dir.exists():
        return []
    # sort so the canonical name (no "(1)" suffix) wins the dedupe
    files = sorted(music_dir.iterdir(), key=lambda p: (_dedupe_key(p.name), "(" in p.name, p.name))
    seen, out = set(), []
    for p in files:
        if p.suffix.lower() in AUDIO_EXTS and not p.name.startswith("."):
            k = _dedupe_key(p.name)
            if k not in seen:
                seen.add(k)
                out.append(p)
    return out


def probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True)
        return float(r.stdout.strip() or 0)
    except Exception:
        return 0.0


class MusicEngine:
    def __init__(self, tracks, seed: int, min_s: float = 4.0, max_s: float = 14.0):
        self.tracks = list(tracks)
        self.rng = random.Random(seed)
        self.min_s, self.max_s = float(min_s), float(max_s)
        self._order = self.tracks[:]
        self.rng.shuffle(self._order)         # day's rotation

    def _cut(self, track, dur, duration_of) -> tuple:
        d = duration_of(track)
        dur = min(dur, max(d - 1.0, 1.0))
        if d - SKIP_INTRO - SKIP_OUTRO >= dur:
            start = self.rng.uniform(SKIP_INTRO, d - SKIP_OUTRO - dur)
        else:                                  # short track: relax the skips
            start = self.rng.uniform(0, max(d - dur, 0))
        return (track, round(start, 2), round(dur, 2))

    def intro_cue(self, intro_s: float, duration_of=probe_duration):
        if not self._order:
            return None
        return self._cut(self._order[0], float(intro_s), duration_of)

    def plan_cues(self, count: int, duration_of=probe_duration) -> list[tuple]:
        """One snippet per segment boundary; rotates through the day's track order."""
        if not self._order or count <= 0:
            return []
        # offset by 1 so the intro track and the first boundary differ
        cues = []
        for i in range(count):
            track = self._order[(i + 1) % len(self._order)]
            dur = self.rng.uniform(self.min_s, self.max_s)
            cues.append(self._cut(track, dur, duration_of))
        return cues


def extract(cue, out_path) -> None:
    """Render a cue (track, start, dur) to a mono 44.1k mp3 with a gentle, gradual fade-out."""
    track, start, dur = cue
    fin = 0.6
    fout = min(3.5, max(dur * 0.5, 1.5))       # long, gradual tail
    subprocess.run(
        ["ffmpeg", "-y", "-ss", str(start), "-t", str(dur), "-i", str(track),
         "-af", f"afade=t=in:st=0:d={fin},afade=t=out:st={max(dur - fout, 0):.2f}:d={fout:.2f},"
                "dynaudnorm=p=0.6,volume=0.9,aformat=channel_layouts=mono:sample_rates=44100",
         "-ac", "1", "-ar", "44100", "-q:a", "4", str(out_path)],
        check=True, capture_output=True)
