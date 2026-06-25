#!/usr/bin/env bash
#
# install.sh — one-shot setup for SIGNAL (daily-briefing).
#
# Sets up everything needed to run the pipeline: checks Python, installs ffmpeg,
# creates the virtualenv + Python deps, and seeds your .env. Idempotent — safe to
# re-run anytime (it won't clobber an existing .env or config).
#
#   ./install.sh
#
# Then:  source .venv/bin/activate   &&   brief config
#
set -euo pipefail
cd "$(dirname "$0")"

# ---- output helpers ----------------------------------------------------------
bold(){ printf '\n\033[1m%s\033[0m\n' "$1"; }
ok(){   printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$1"; }
err(){  printf '  \033[31m✗\033[0m %s\n' "$1" >&2; }
have(){ command -v "$1" >/dev/null 2>&1; }
# ask "question" -> yes by default; auto-skips (no) when not run interactively.
ask(){ [ -t 0 ] || return 1; local a; read -r -p "  $1 [Y/n] " a; [[ "${a:-Y}" =~ ^[Yy] ]]; }

OS="$(uname -s)"
bold "SIGNAL setup · $OS"

# ---- 1. Python 3.11+ ---------------------------------------------------------
PYBIN=""
for c in python3.13 python3.12 python3.11 python3; do
  have "$c" || continue
  v="$("$c" -c 'import sys;print("%d %d"%sys.version_info[:2])' 2>/dev/null || echo "0 0")"
  set -- $v
  if [ "$1" -eq 3 ] && [ "$2" -ge 11 ]; then PYBIN="$c"; break; fi
done
if [ -z "$PYBIN" ]; then
  err "Python 3.11+ not found."
  warn "Install it — macOS: brew install python   |   Debian/Ubuntu: sudo apt install python3 python3-venv"
  exit 1
fi
ok "Python $("$PYBIN" -c 'import sys;print("%d.%d.%d"%sys.version_info[:3])') ($PYBIN)"

# ---- 2. ffmpeg ---------------------------------------------------------------
if have ffmpeg; then
  ok "ffmpeg present"
else
  warn "ffmpeg not found (needed to stitch the audio)."
  if [ "$OS" = "Darwin" ] && have brew; then
    ask "Install ffmpeg with Homebrew now?" && brew install ffmpeg && ok "ffmpeg installed"
  elif have apt-get; then
    ask "Install ffmpeg with apt now (needs sudo)?" && sudo apt-get update -qq && sudo apt-get install -y ffmpeg && ok "ffmpeg installed"
  elif have dnf; then
    ask "Install ffmpeg with dnf now (needs sudo)?" && sudo dnf install -y ffmpeg && ok "ffmpeg installed"
  elif have pacman; then
    ask "Install ffmpeg with pacman now (needs sudo)?" && sudo pacman -S --noconfirm ffmpeg && ok "ffmpeg installed"
  fi
  have ffmpeg || warn "ffmpeg still missing — install it before ./make_briefing.sh (brew install ffmpeg / apt install ffmpeg)."
fi

# ---- 3. virtualenv + Python deps --------------------------------------------
if [ -d .venv ]; then
  ok "virtualenv .venv exists"
else
  "$PYBIN" -m venv .venv && ok "created virtualenv .venv"
fi
printf '  … installing Python dependencies (this can take a minute)\n'
./.venv/bin/python -m pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -e ".[dev]"
ok "Python dependencies installed"

# ---- 3b. bumper music (optional; fetched from the GitHub Release) ------------
# Tracks aren't in git (see briefing/assets/ATTRIBUTION.md); the renderer falls back
# to a generated bumper if they're absent, so this is best-effort.
MUSIC_REPO="acsousa/daily-briefing"
MUSIC_URL="https://github.com/$MUSIC_REPO/releases/latest/download/briefing-music.zip"
MUSIC_ZIP="${BRIEF_MUSIC_ZIP:-briefing-music.zip}"   # a zip you placed here (scp'd in); gh-free
if ls briefing/assets/*.mp3 >/dev/null 2>&1; then
  ok "bumper music present"
elif ! have unzip; then
  warn "unzip not available — skipping bumper music (a generated bumper is used instead)."
else
  printf '  … installing bumper music (optional)\n'
  src=""
  if [ -f "$MUSIC_ZIP" ]; then
    src="$MUSIC_ZIP"                               # 1) a local zip dropped next to install.sh
  elif have curl && curl -fsSL "$MUSIC_URL" -o /tmp/signal-music.zip 2>/dev/null; then
    src="/tmp/signal-music.zip"                    # 2) public release download (no auth needed)
  elif have gh && gh release download --repo "$MUSIC_REPO" --pattern briefing-music.zip \
         --output /tmp/signal-music.zip --clobber 2>/dev/null; then
    src="/tmp/signal-music.zip"                    # 3) private release via gh, only if installed
  fi
  if [ -n "$src" ] && unzip -oq "$src" -d briefing/assets 2>/dev/null; then
    ok "bumper music installed ($(ls briefing/assets/*.mp3 2>/dev/null | wc -l | tr -d ' ') tracks)"
    [ "$src" = "/tmp/signal-music.zip" ] && rm -f /tmp/signal-music.zip
  else
    warn "no bumper music yet — using a generated one. To add the tracks:"
    warn "  download briefing-music.zip from the repo's Releases page, scp it into this folder,"
    warn "  and re-run ./install.sh — or just drop your own no-lyric .mp3s into briefing/assets/."
  fi
fi

# ---- 4. .env (Anthropic API key) --------------------------------------------
if [ -f .env ] && grep -qE 'ANTHROPIC_API_KEY=sk-' .env; then
  ok ".env already has an API key"
else
  key=""
  [ -t 0 ] && read -r -p "  Paste your Anthropic API key (sk-ant-… , or Enter to set later): " key || true
  if [ -n "${key:-}" ]; then
    printf 'ANTHROPIC_API_KEY=%s\n' "$key" > .env
    ok "wrote .env"
  else
    [ -f .env ] || printf 'ANTHROPIC_API_KEY=sk-ant-REPLACE_ME\n' > .env
    warn "no key set yet — edit .env and set ANTHROPIC_API_KEY before 'brief generate'."
  fi
fi

# ---- 5. finishing touches ----------------------------------------------------
chmod +x make_briefing.sh run_daily.sh install.sh 2>/dev/null || true
if ./.venv/bin/brief --help >/dev/null 2>&1; then ok "brief CLI ready"; else err "brief CLI failed to load"; exit 1; fi

bold "Done. Next steps:"
cat <<'EOF'
  source .venv/bin/activate     # activate the env — then `brief` works without the path
  brief config                  # set name, interests, voices, show name… in the browser
  brief generate                # build today's script
  ./make_briefing.sh            # render the MP3 (and publish, if Spotify is set up)

  Optional:
    brief schedule              # run it automatically every morning (launchd/systemd/cron)
    curl -fsSL https://saveto.spotify.com/install.sh | bash && save-to-spotify auth login
EOF
