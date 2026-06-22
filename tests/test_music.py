"""Music snippet engine — selection logic (no ffmpeg/ffprobe in tests)."""
from pathlib import Path

from briefing.render.music import MusicEngine, list_tracks


def test_list_tracks_dedupes_and_filters(tmp_path):
    for n in ["a.mp3", "a (1).mp3", "b.wav", "cover.jpg", ".hidden.mp3"]:
        (tmp_path / n).write_bytes(b"x")
    names = sorted(p.name for p in list_tracks(tmp_path))
    assert names == ["a.mp3", "b.wav"]          # "(1)" dup folded; non-audio + hidden skipped


def _durs(*tracks):
    return {t: d for t, d in tracks}


def test_plan_cues_count_lengths_and_bounds():
    tracks = [Path("t1"), Path("t2"), Path("t3")]
    durs = {Path("t1"): 120.0, Path("t2"): 90.0, Path("t3"): 200.0}
    cues = MusicEngine(tracks, seed=20260622, min_s=5, max_s=10).plan_cues(
        6, duration_of=lambda t: durs[t])
    assert len(cues) == 6
    for track, start, dur in cues:
        assert 1.0 <= dur <= 10.0
        assert start >= 0 and start + dur <= durs[track]


def test_rotation_varies_by_day_seed():
    tracks = [Path("t1"), Path("t2"), Path("t3")]
    durs = {t: 120.0 for t in tracks}
    a = MusicEngine(tracks, 20260622, 5, 10).plan_cues(4, duration_of=lambda t: durs[t])
    b = MusicEngine(tracks, 20260623, 5, 10).plan_cues(4, duration_of=lambda t: durs[t])
    assert a != b                                # different days produce different cues


def test_short_track_relaxes_skips():
    t = Path("short")
    cue = MusicEngine([t], 1, 5, 14).plan_cues(1, duration_of=lambda _: 6.0)[0]
    _, start, dur = cue
    assert dur >= 1.0 and start + dur <= 6.0


def test_intro_uses_requested_length():
    t = Path("t1")
    _, _, dur = MusicEngine([t], 1, 4, 8).intro_cue(12, duration_of=lambda _: 120.0)
    assert abs(dur - 12.0) < 0.01
