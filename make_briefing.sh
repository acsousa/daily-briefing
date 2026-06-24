#!/usr/bin/env bash
#
# make_briefing.sh — daily two-host audio-briefing pipeline
#
# Pipeline: briefing.txt --(render_briefing.py: edge-tts + ffmpeg)--> briefing-DATE.mp3
#           --(save-to-spotify)--> "Andrew's Daily Rundown" on Spotify
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
TITLE="$("$PY" - <<'PY' 2>/dev/null || echo 'Daily Briefing'
from briefing.config import load_profile
n = ((load_profile().get('owner') or {}).get('name') or '').split()
print((n[0] + "'s Daily Briefing") if n else 'Daily Briefing')
PY
)"
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
lo, hi = t * 0.6, t * 1.4          # generous +/-40% buffer
status = "ok" if lo <= a <= hi else "WARNING — outside target buffer"
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

echo ">> Uploading to Spotify"
RESULT=$("$STS" --json upload "$OUT" \
  --title "$TITLE — $PRETTY_DATE" \
  --summary "Your daily news briefing: top stories, markets, and the day ahead." \
  --show-id "$SHOW_ID")
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
