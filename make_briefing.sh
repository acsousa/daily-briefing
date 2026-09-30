#!/usr/bin/env bash
#
# make_briefing.sh — daily two-host audio-briefing pipeline
#
# Pipeline: briefing.txt --(render_briefing.py: edge-tts + ffmpeg)--> briefing-DATE.mp3
#           --(save-to-spotify)--> your show on Spotify
#
# Run from this directory:  ./make_briefing.sh
# Cron-safe: uses the binary's full path (cron does not load ~/.bash_profile).
#
set -euo pipefail
cd "$(dirname "$0")"

# ---- config -----------------------------------------------------------------
PY="python3"; [ -x ".venv/bin/python" ] && PY=".venv/bin/python"
# Resolve the save-to-spotify CLI: PATH, then ~/.local/bin, then /usr/local/bin.
STS="$(command -v save-to-spotify 2>/dev/null || true)"
[ -z "$STS" ] && [ -x "$HOME/.local/bin/save-to-spotify" ] && STS="$HOME/.local/bin/save-to-spotify"
[ -z "$STS" ] && [ -x "/usr/local/bin/save-to-spotify" ] && STS="/usr/local/bin/save-to-spotify"
# Show id + episode title come from config / profile (not hard-coded to one user).
SHOW_ID="$("$PY" -c "from briefing.config import load_config; print((load_config().get('spotify') or {}).get('show_id',''))" 2>/dev/null || true)"
# Episode title = the show name. Prefer config spotify.show_name; otherwise ask Spotify
# for the real show title (authoritative); otherwise fall back to "<First>'s Daily Briefing".
TITLE="$("$PY" -c "from briefing.config import load_config; print(((load_config().get('spotify') or {}).get('show_name') or '').strip())" 2>/dev/null || true)"
if [ -z "$TITLE" ] && [ -n "${STS:-}" ] && [ -x "$STS" ] && [ -n "${SHOW_ID:-}" ]; then
  TITLE="$("$STS" --json shows 2>/dev/null | "$PY" -c 'import sys,json;sid=sys.argv[1];d=json.load(sys.stdin).get("shows",[]);m=[s for s in d if s.get("show_uri")==sid];print(m[0]["title"] if m else "")' "$SHOW_ID" 2>/dev/null || true)"
fi
if [ -z "$TITLE" ]; then
  TITLE="$("$PY" - <<'PY' 2>/dev/null || echo 'Daily Briefing'
from briefing.config import load_profile
n = ((load_profile().get('owner') or {}).get('name') or '').split()
print((n[0] + "'s Daily Briefing") if n else 'Daily Briefing')
PY
)"
fi
# Voice / tempo / gaps / music are configured under render: in config.yaml
# -----------------------------------------------------------------------------

DATE="$(date +%Y-%m-%d)"
PRETTY_DATE="$(date +'%B %-d, %Y')"
OUT="briefings/briefing-$DATE.mp3"

# Step A — (agent step) regenerate briefings/briefing.txt with today's content.
#          Currently it holds a sample script. Have the agent rewrite it
#          (ARIA:/ANDREW: tagged lines) before running for a real briefing.

# Step B — render two-host audio (edge-tts per turn + ffmpeg stitch)
# Prefer the venv Python so the renderer can read config (rate, gaps, sting).
echo ">> Rendering audio: $OUT"
PY="python3"; [ -x ".venv/bin/python" ] && PY=".venv/bin/python"
"$PY" render_briefing.py

# Sanity check: is the rendered audio close to the target duration?
TARGET_MIN=$("$PY" -c "from briefing.config import load_config; print(load_config().get('episode',{}).get('target_duration_minutes',20))" 2>/dev/null || echo 20)
ACTUAL_MIN=$(ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "$OUT" 2>/dev/null | awk '{printf "%.1f", $1/60}')
"$PY" - "$ACTUAL_MIN" "$TARGET_MIN" <<'PY'
import sys
a, t = float(sys.argv[1] or 0), float(sys.argv[2])
lo, hi = t - 3, t + 3              # within +/-3 minutes of target
status = "ok" if lo <= a <= hi else "WARNING — outside target window"
print(f">> Duration: {a:.1f}m (target {t:.0f}m, accept {lo:.0f}-{hi:.0f}m) — {status}")
PY

# Step C — publish to Spotify (skipped gracefully if not set up)
if [ -z "${STS:-}" ] || [ ! -x "$STS" ]; then
  echo ">> save-to-spotify not found — skipping upload. Audio ready: $OUT"
  exit 0
fi
if [ -z "${SHOW_ID:-}" ] || printf '%s' "$SHOW_ID" | grep -q 'REPLACE_ME'; then
  echo ">> spotify.show_id not configured — skipping upload. Audio ready: $OUT"
  exit 0
fi
# Freshness guard: don't publish a stale script. episode.json carries the generate date.
EP_DATE="$("$PY" -c "import json;print(json.load(open('briefings/episode.json')).get('date',''))" 2>/dev/null || true)"
if [ "$EP_DATE" != "$DATE" ] && [ "${BRIEF_ALLOW_STALE:-0}" != "1" ]; then
  echo ">> briefing is from '${EP_DATE:-unknown}', not today ($DATE) — run \`brief generate\` first."
  echo ">> Skipping upload. (Set BRIEF_ALLOW_STALE=1 to publish anyway.) Audio: $OUT"
  exit 0
fi

echo ">> Uploading to Spotify"
# briefing.publish prunes the oldest episodes to stay under spotify.max_episodes (default 55;
# Spotify refuses uploads at 60), then uploads. Progress/errors go to stderr (this log).
if ! RESULT=$("$PY" -m briefing.publish --sts "$STS" --show-id "$SHOW_ID" upload "$OUT" \
  --title "$TITLE — $PRETTY_DATE" \
  --summary "Your daily news briefing: top stories, markets, and the day ahead."); then
  echo "!! Upload failed (see error above). Audio ready: $OUT"
  exit 1
fi
echo "$RESULT"

EP_URI=$(echo "$RESULT" | "$PY" -c 'import sys,json;print(json.load(sys.stdin)["episode_uri"])')
EP_ID=${EP_URI#spotify:episode:}

echo ">> Waiting for episode to be READY ($EP_ID)"
for i in $(seq 1 20); do
  R=$("$STS" --json episodes status "$EP_ID" \
      | "$PY" -c 'import sys,json;print(json.load(sys.stdin).get("readiness","?"))')
  echo "   poll $i: $R"
  [ "$R" = "READY" ] && break
  [ "$R" = "FAILED" ] && echo "Processing failed" && exit 1
  sleep 15
done

echo ">> Done: $EP_URI"
