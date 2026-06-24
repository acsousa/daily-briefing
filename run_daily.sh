#!/usr/bin/env bash
#
# run_daily.sh — the scheduled daily job: generate → render → upload.
# Invoked by launchd (see `brief schedule`). Logs to briefings/run-DATE.log.
#
set -uo pipefail
cd "$(dirname "$0")"

# launchd/cron/systemd have a minimal PATH; add common bin dirs (macOS + Linux) and keep $PATH.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/home/linuxbrew/.linuxbrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
mkdir -p briefings
LOG="briefings/run-$(date +%Y-%m-%d).log"

{
  echo "=================================================================="
  echo "=== $(date)  SIGNAL daily briefing ==="
  echo ">> generate"
  "$PY" -m briefing.cli generate || { echo "!! generate failed"; exit 1; }
  echo ">> render + upload"
  ./make_briefing.sh || { echo "!! make_briefing failed"; exit 1; }
  echo ">> done $(date)"
} >> "$LOG" 2>&1
