# SIGNAL — your daily intelligence briefing

SIGNAL turns each day's news into a personalized, two-host audio briefing and (optionally)
publishes it to your Spotify every morning — automatically. You set your interests, length,
voices, and tone once; each day it sources real news, writes a grounded, news-first script
in the style of *Marketplace*, narrates it with two AI hosts over music, and produces an MP3.

Runs on **macOS and Linux**.

```
your config → fetch real news → cluster · rank · plan → editor + scriptwriter (Claude)
   → two-host audio (edge-tts + ffmpeg, your music) → MP3 → (optional) Spotify
```

## What you need

| Requirement | Why | Notes |
|---|---|---|
| **Python 3.11+** | runs the pipeline | macOS or Linux |
| **ffmpeg** | stitches the audio | `brew install ffmpeg` / `apt install ffmpeg` |
| **Anthropic API key** | the editor + scriptwriter (Claude) | pay-as-you-go, ~$1–3/episode — [console](https://platform.claude.com) |
| **save-to-spotify** *(optional)* | publishes to Spotify | skip it and you still get the MP3 |
| **Music tracks** *(optional)* | bumpers between segments | drop no-lyric mp3s in `briefing/assets/` (e.g. Pixabay) |

## Setup

```sh
# 1. Get the code + a virtualenv with all Python deps
git clone https://github.com/acsousa/daily-briefing.git
cd daily-briefing
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

# 2. System audio tool
brew install ffmpeg        # macOS
sudo apt install ffmpeg    # Debian/Ubuntu

# 3. Your Anthropic API key (gitignored)
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env

# 4. Set your preferences (web UI → writes profile.yaml / config.yaml)
.venv/bin/brief config     # opens http://127.0.0.1:8765

# 5. Build today's episode
.venv/bin/brief generate   # → briefings/briefing.txt + episode.json
./make_briefing.sh         # render to MP3 (and publish, if Spotify is set up)
```

That's it for local audio. **Publishing and scheduling are optional** (below).

### Publish to Spotify (optional)

Uses Spotify's official [`save-to-spotify`](https://github.com/spotify/save-to-spotify) CLI
(macOS + Linux builds). Install and authenticate once:

```sh
curl -fsSL https://saveto.spotify.com/install.sh | bash   # detects your OS/arch
save-to-spotify auth login                                # one-time browser login
```

Then set `spotify.show_id` in `config.yaml` (run `save-to-spotify shows` to get it).
`make_briefing.sh` uploads automatically; if `save-to-spotify` or the show id is missing, it
just **skips the upload** and leaves you the MP3.

### Run it daily (optional)

```sh
.venv/bin/brief schedule          # install the daily run; --uninstall to remove
```

It runs `lead_hours` before your `drop_time` (both set in `brief config`). The mechanism is
chosen for your OS automatically: **launchd** on macOS, a **systemd user timer** on Linux
(or **cron** if systemd isn't available). The machine must be on at that time.

## Configure

`brief config` is the easy path. Under the hood, two gitignored files (copy from the
committed `*.example.yaml`):

- **`profile.yaml`** — you: interests + weights, region focus, style/tone, favor/avoid.
- **`config.yaml`** — operational: source feeds, weather location, length, voices, drop
  time, music, and the Claude models.

## Commands

```sh
brief config                 # web UI to edit your preferences
brief generate               # build today's script (briefing.txt + episode.json)
brief generate --dry-run     # plan only, no API calls
brief ingest                 # just fetch + filter + store articles
brief schedule               # install/uninstall the daily run
./make_briefing.sh           # render the script to audio (+ optional publish)
```

Remote Linux server? `brief config` binds localhost; reach it over an SSH tunnel
(`ssh -L 8765:127.0.0.1:8765 you@server`) or edit the YAML directly.

## Notes

- The `generate → script → audio` core is fully platform-independent.
- Episodes on Spotify are personal content; audio is stored on Spotify's servers and subject
  to their moderation — don't put sensitive info in a briefing.
- The Claude API is pay-as-you-go and separate from a Claude.ai subscription; add credits at
  platform.claude.com.

Architecture detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
