# Save to Spotify — Setup & Daily Briefing Workflow

This file is a handoff for a new Claude Cowork session. It explains how to install
Spotify's official **Save to Spotify** CLI and build a daily audio-briefing workflow
that generates a briefing, converts it to audio, and uploads it to Spotify.

---

## What this is

`Save to Spotify` is an official, open-source CLI from Spotify
(`https://github.com/spotify/save-to-spotify`, Apache-2.0). It saves audio files to
Spotify as podcast-style episodes inside "shows." It is built for agents/automation.

**Important:** the CLI only *uploads* audio. It does **not** generate audio. A briefing
workflow therefore has three parts: (1) write the briefing text, (2) convert text →
speech (TTS) to make an `.mp3`, (3) upload the `.mp3` with the CLI.

---

## Trust / safety notes (read before installing)

- The repo is genuinely under the real `spotify` GitHub org and the install host
  `saveto.spotify.com` is Spotify's. The README's quick-start is a `curl … | bash`
  pipe — that pattern runs remote code unread, so prefer the plugin-marketplace or
  manual+checksum paths below instead.
- The Spotify **login is a one-time browser OAuth step that only the human can
  complete** — an agent cannot authorize on its own. Expect to open a URL and approve.
- Don't paste auth tokens into chat. The CLI stores its own token at
  `~/.config/save-to-spotify/token.json` and refreshes it automatically.

---

## Step 1 — Install the CLI (preferred: Claude Code plugin marketplace)

These are Claude Code CLI commands the **user** types into their own Claude Code
session (an agent cannot run the plugin installer for them):

```
/plugin marketplace add spotify/save-to-spotify
/plugin install save-to-spotify@save-to-spotify
```

### Alternative A — Manual install with checksum verification (most transparent)

1. Go to the releases page: https://github.com/spotify/save-to-spotify/releases
2. Download `save-to-spotify-{os}-{arch}-v{version}.zip` **and** its `.sha256`.
   (e.g. `save-to-spotify-darwin-arm64-v0.1.1.zip` on Apple Silicon Macs.)
3. Verify integrity before unzipping:
   ```
   shasum -c save-to-spotify-darwin-arm64-v0.1.1.zip.sha256
   ```
4. Unzip, move the `save-to-spotify` binary to a directory on your `PATH`
   (e.g. `~/.local/bin` or `/usr/local/bin`), and `chmod +x` it.

### Alternative B — Curl-bash (Spotify's documented quick path; runs unread code)

```
curl -fsSL https://saveto.spotify.com/install.sh | bash
```
Only use this if you've decided to trust the pipe. To inspect first, fetch the script
and read it before running anything.

### Verify install

```
save-to-spotify version
```

---

## Step 2 — Authenticate (user-only step)

```
save-to-spotify auth login
```

This opens the browser to authorize with Spotify and grant permission to upload
personal content. Confirm it worked:

```
save-to-spotify auth status
```

For SSH/remote machines use `save-to-spotify auth login --no-browser`, which prints a
URL to open on any device, then you paste back the redirect URL.

---

## Step 3 — Generate the briefing audio

The CLI does not make audio, so produce an `.mp3` first.

### 3a. Write the briefing text
The Cowork agent can generate the briefing copy (news, weather, calendar). Save it as a
plain-text or markdown script, e.g. `briefing.txt`. Keep it conversational and read
aloud-friendly; aim for ~1–3 minutes of speech.

### 3b. Convert text → speech (pick one TTS engine)

- **edge-tts** (free, good quality, cross-platform Python tool):
  ```
  pip install edge-tts --break-system-packages
  edge-tts --voice en-US-AriaNeural --file briefing.txt --write-media briefing.mp3
  ```
- **macOS `say`** (built in; produces `.aiff`, convert to mp3 with ffmpeg):
  ```
  say -f briefing.txt -o briefing.aiff
  ffmpeg -i briefing.aiff briefing.mp3
  ```
- **ElevenLabs** (highest quality, needs an API key) — use their API/CLI to render mp3.

Supported upload formats: `.mp3`, `.m4a`, `.wav`, `.ogg`.

---

## Step 4 — Upload to Spotify

First run creates a show automatically (or target/create one explicitly):

```
# Simplest — uses your most recent show, or creates one
save-to-spotify upload ./briefing.mp3 \
  --title "Morning Briefing — <DATE>" \
  --summary "Weather and calendar for today"

# Put briefings in their own dedicated show (recommended for a recurring series)
save-to-spotify upload ./briefing.mp3 \
  --title "Morning Briefing — <DATE>" \
  --new-show "Daily Briefing"

# Add cover art (jpg/png, max 1 MB)
save-to-spotify upload ./briefing.mp3 --title "Morning Briefing — <DATE>" --image ./cover.jpg
```

After the first run, reuse the show with `--show-id`:
```
save-to-spotify shows                       # list shows, copy the id/uri
save-to-spotify upload ./briefing.mp3 --title "…" --show-id spotify:show:<id>
```

Confirm playback readiness (episodes process for a few minutes):
```
save-to-spotify episodes status <episode-id> --wait
```

---

## Step 5 — One-command daily script (optional)

Have the Cowork agent assemble a script (`make_briefing.sh`) that chains everything:

```bash
#!/usr/bin/env bash
set -euo pipefail

DATE="$(date +%Y-%m-%d)"
OUT="briefing-$DATE.mp3"

# 1. (Agent step) generate briefing.txt — news + weather + calendar
# 2. TTS → mp3
edge-tts --voice en-US-AriaNeural --file briefing.txt --write-media "$OUT"
# 3. Upload to the dedicated show
save-to-spotify upload "$OUT" \
  --title "Morning Briefing — $DATE" \
  --summary "Top news, weather, and today's calendar" \
  --show-id "spotify:show:<YOUR_SHOW_ID>"
```

To run it automatically each morning, schedule it on the user's machine (e.g. `cron`,
`launchd`, or a Cowork scheduled task that triggers the local run). Note the upload must
run on the machine where the CLI is authenticated.

---

## JSON mode for agents

Every command supports `--json` for scripting:
```
save-to-spotify --json auth status
save-to-spotify --json shows | jq '.shows[].title'
save-to-spotify --json upload ./briefing.mp3 --title "Ep 1" | jq -r .episode_uri
```
Errors come back as `{"error": "message"}`.

---

## Useful reference

- Repo + full README: https://github.com/spotify/save-to-spotify
- Releases (for manual install + checksums): https://github.com/spotify/save-to-spotify/releases
- Spotify help article: https://support.spotify.com/us/article/save-to-spotify/
- Usage limits (beta): Free = 5 shows / 30 episodes each; Premium = 10 shows / 60 each.
- Content must be primarily talk content, not music; follow Spotify Platform Rules.

---

## Quick checklist for the next session

- [ ] Install CLI (plugin marketplace preferred; manual+checksum as fallback)
- [ ] `save-to-spotify auth login` (user opens browser, authorizes)
- [ ] `save-to-spotify auth status` shows logged in
- [ ] Decide briefing contents + user's city for weather
- [ ] Generate `briefing.txt`, render to `briefing.mp3` via TTS
- [ ] Create/choose a "Daily Briefing" show, upload first episode
- [ ] (Optional) Build `make_briefing.sh` and schedule it
