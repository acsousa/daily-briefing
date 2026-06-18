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
STS="$HOME/.local/bin/save-to-spotify"          # full path; cron has no PATH
SHOW_ID="spotify:show:033AAkPmapL99eyKwK0UQO"   # Andrew's Daily Rundown
SHOW_TITLE="Andrew's Daily Rundown"
# Voice / tempo / gaps are configured at the top of render_briefing.py
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

# Step C — upload to the dedicated show, poll until READY
echo ">> Uploading to Spotify"
RESULT=$("$STS" --json upload "$OUT" \
  --title "$SHOW_TITLE — $PRETTY_DATE" \
  --summary "Your two-host daily briefing: weather, headlines, and the day ahead." \
  --show-id "$SHOW_ID")
echo "$RESULT"

EP_URI=$(echo "$RESULT" | python3 -c 'import sys,json;print(json.load(sys.stdin)["episode_uri"])')
EP_ID=${EP_URI#spotify:episode:}

echo ">> Waiting for episode to be READY ($EP_ID)"
for i in $(seq 1 20); do
  R=$("$STS" --json episodes status "$EP_ID" \
      | python3 -c 'import sys,json;print(json.load(sys.stdin).get("readiness","?"))')
  echo "   poll $i: $R"
  [ "$R" = "READY" ] && break
  [ "$R" = "FAILED" ] && echo "Processing failed" && exit 1
  sleep 15
done

echo ">> Done: $EP_URI"
