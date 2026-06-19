# SIGNAL — your daily intelligence briefing

SIGNAL turns the day's news into a personalized, two-host audio briefing and publishes it
to your Spotify every morning — automatically, on a schedule. You set your interests, length,
voices, and tone once; each day it sources real news, writes a grounded script in the style of
*Marketplace*, narrates it with two AI hosts, and uploads the episode before your commute.

```
your interests → fetch real news → cluster · rank · plan → editor + scriptwriter (Claude)
   → two-host audio (edge-tts + ffmpeg, with music stings) → publish to Spotify
```

## Features

- **Personalized.** A topic-weighted interest profile (tech, defense, business, science, …)
  decides what's covered; a relevance filter keeps only what's yours and drops the rest.
- **Genuinely good copy.** An editorial pass (Claude Opus) finds the tension in each story and
  the connections across them; a scriptwriter turns it into conversational two-host dialogue —
  substance first, market-moves as a footnote, dry wit, no jargon.
- **Grounded, not hallucinated.** Every claim traces to a fetched source; facts stay separate
  from analysis; nothing is invented.
- **Continuity.** It remembers what it told you across days/weeks and builds on developing
  stories instead of repeating them.
- **Two AI hosts, your voices.** Pick a male/female voice pair; natural pacing, verbal
  hand-offs, and short music stings between segments.
- **Commute-length control.** A 5–30 minute slider; a sanity check flags if a build drifts
  from your target.
- **Hands-off.** A one-screen web config and a daily macOS schedule — set it and forget it.

## Requirements

| Need | Why |
|------|-----|
| **macOS**, **Python 3.11+** | the pipeline + the daily scheduler (launchd) |
| **ffmpeg** (`brew install ffmpeg`) | stitches the audio |
| **Anthropic API key** | the editor + scriptwriter (Claude). Pay-as-you-go; ~$1–3/episode |
| **Spotify `save-to-spotify` CLI** | publishes the episode (free, official Spotify CLI) |

## Setup

```sh
# 1. Install
git clone https://github.com/acsousa/daily-briefing.git
cd daily-briefing
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
brew install ffmpeg

# 2. Add your Anthropic API key (gitignored)
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env

# 3. Install + authenticate the Spotify CLI (one-time browser login)
#    See docs/SAVE_TO_SPOTIFY_SETUP.md for the install command.
save-to-spotify auth login

# 4. Set your preferences (opens the SIGNAL web UI)
.venv/bin/brief config

# 5. Build & publish today's episode once to confirm it works
.venv/bin/brief generate && ./make_briefing.sh

# 6. Schedule it to run every day on your Mac
.venv/bin/brief schedule
```

### Required inputs

- **`ANTHROPIC_API_KEY`** in `.env` (the only secret).
- **Spotify auth** via `save-to-spotify auth login` (one-time).
- **Your preferences** via `brief config` (name, interests, length, drop time, voices, tone,
  favor/avoid) — saved to `profile.yaml` / `config.yaml`.

## Usage

```sh
brief config            # web UI to edit your preferences (writes profile.yaml/config.yaml)
brief generate          # build today's script → briefings/briefing.txt + episode.json
brief generate --dry-run   # plan only, no API calls
./make_briefing.sh      # render the script to audio and publish to Spotify
brief schedule          # install the daily run (drop_time − lead_hours); --uninstall to remove
```

The daily schedule runs `lead_hours` before your `drop_time` (default: 2 hours before 8 AM →
6 AM). Your Mac must be awake or asleep — launchd runs the job on wake if it was missed; it
won't run while fully powered off.

## Configuration

Two user files (gitignored; copy from the committed `*.example.yaml`, or just use `brief config`):

- **`profile.yaml`** — *you*: interests + weights, style/tone, host personas, favor/avoid.
- **`config.yaml`** — *operational*: source feeds, weather location, target length, drop time,
  voices, and the LLM models. A broad default source catalog is inherited from
  `config.example.yaml`; add your own (e.g. local) feeds.

## How it works

`brief generate` runs ingest → cluster → rank (with novelty vs. prior episodes) → plan
(duration-budgeted) → fetch full text → **editor** (Claude Opus) → **scriptwriter** (Claude)
→ `briefing.txt` + `episode.json`. `make_briefing.sh` renders the two voices with edge-tts,
stitches with ffmpeg (music stings between segments), and uploads via the Spotify CLI.
Architecture detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Notes

- Episodes are **personal content** on Spotify (per Spotify, can't be shared). Audio is stored
  on Spotify's servers and subject to their moderation — don't put sensitive info in a briefing.
- The Claude API is pay-as-you-go and separate from a Claude.ai subscription; add credits at
  platform.claude.com.
- Built on the official Spotify [`save-to-spotify`](https://github.com/spotify/save-to-spotify) CLI.
