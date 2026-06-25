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
| **Anthropic API key** | the editor + scriptwriter (Claude) | pay-as-you-go, <$1/episode — [console](https://platform.claude.com) |
| **save-to-spotify** | publishes the episode so you can listen | or play the MP3 in any podcast/news app you like |

A set of royalty-free bumper tracks ships in `briefing/assets/` — the music engine rotates
them automatically. Drop your own no-lyric mp3s there to personalize it.

## Setup

```sh
# 1. Get the code
git clone https://github.com/acsousa/daily-briefing.git
cd daily-briefing

# 2. One-shot install — Python venv + deps, ffmpeg, and your .env
./install.sh               # idempotent; prompts for ffmpeg + your Anthropic API key

# 3. Activate the env (now `brief` works without a path prefix)
source .venv/bin/activate

# 4. Configure everything in the browser — name, interests, voices, show name, Spotify id
brief config               # opens http://127.0.0.1:8765

# 5. Build today's episode
brief generate             # → briefings/briefing.txt + episode.json
./make_briefing.sh         # render to MP3, then publish to your show
```

`./install.sh` is safe to re-run and won't clobber your `.env` or config. If you'd rather do
it by hand, the steps it runs are right there in [`install.sh`](install.sh).

### Publish to Spotify (optional)

```sh
curl -fsSL https://saveto.spotify.com/install.sh | bash   # detects your OS/arch
save-to-spotify auth login                                # one-time browser login
```

Then put your **show id** in `brief config` (run `save-to-spotify shows` to find it). If it's
not set, `make_briefing.sh` just **skips the upload** and leaves you the MP3 to play in any
podcast/news app.

### Run it daily (optional)

```sh
brief schedule          # install the daily run; --uninstall to remove
```

It builds a fixed **2 hours** before your `drop_time` (set in `brief config`). The mechanism is
chosen for your OS automatically: **launchd** on macOS, a **systemd user timer** on Linux
(or **cron** if systemd isn't available). The machine must be on at that time.

## Configure

`brief config` is the easy path — it writes two gitignored files (seeded from the committed
`*.example.yaml`):

- **`profile.yaml`** — you: headline focus + broader interests, region of focus, tone.
- **`config.yaml`** — operational: source feeds, weather location, length, voices, drop
  time, music, Spotify show, and the Claude models.

The page covers everything; deep knobs (ranking weights, always-cover/avoid, music) live under
its **Advanced** section.

## Commands

```sh
brief config                 # web UI to edit your preferences
brief generate               # build today's script (briefing.txt + episode.json)
brief generate --dry-run     # plan only, no API calls
brief ingest                 # just fetch + filter + store articles
brief schedule               # install/uninstall the daily run
./make_briefing.sh           # render the script to audio (+ optional publish)
```

(Commands assume the venv is active — `source .venv/bin/activate`. Otherwise prefix with
`.venv/bin/`.)

Remote Linux server? `brief config` binds localhost; reach it over an SSH tunnel
(`ssh -L 8765:127.0.0.1:8765 you@server`) or edit the YAML directly.

## Notes

- The `generate → script → audio` core is fully platform-independent.
- Episodes on Spotify are personal content; audio is stored on Spotify's servers and subject
  to their moderation — don't put sensitive info in a briefing.
- The Claude API is pay-as-you-go and separate from a Claude.ai subscription; add credits at
  platform.claude.com.

Architecture detail: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
