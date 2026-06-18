# Daily Briefing → Spotify

A small pipeline that turns a written daily briefing into a **two-host audio episode**
and saves it to Spotify as a private podcast episode using Spotify's official
[`save-to-spotify`](https://github.com/spotify/save-to-spotify) CLI.

Episode = `briefing.txt` → (edge-tts renders each host's lines, ffmpeg stitches them)
→ `briefing-YYYY-MM-DD.mp3` → uploaded to the **"Andrew's Daily Rundown"** show.

## Files

| File | Purpose |
|------|---------|
| `briefing.txt` | The day's script. One line per turn, tagged `ARIA:` / `ANDREW:`. |
| `render_briefing.py` | Renders both voices (edge-tts) at a faster tempo, inserts short gaps, stitches to a dated MP3 (ffmpeg). Config — voices, rate, gap — is at the top. |
| `make_briefing.sh` | Full pipeline: render → upload to the show → poll until the episode is `READY`. |
| `SAVE_TO_SPOTIFY_SETUP.md` | Original setup/handoff notes for installing and authenticating the CLI. |

## Prerequisites

- **edge-tts** — `pip install edge-tts` (TTS engine; free)
- **ffmpeg** — `brew install ffmpeg` (stitches the two voices, generates the gaps)
- **save-to-spotify** — install the binary and authenticate once:
  ```sh
  # install (manual + checksum is the transparent path; see SAVE_TO_SPOTIFY_SETUP.md)
  save-to-spotify auth login      # one-time browser OAuth
  save-to-spotify auth status     # confirm
  ```

## Usage

1. Edit `briefing.txt` with the day's content (keep the `ARIA:` / `ANDREW:` tags).
2. Run the pipeline:
   ```sh
   ./make_briefing.sh
   ```
   It renders the audio, uploads it to the show, and waits until the episode is playable.

To preview locally without uploading, just render:
```sh
python3 render_briefing.py     # writes briefing-YYYY-MM-DD.mp3
```

## Notes

- Generated `.mp3` files are git-ignored — they're build artifacts.
- Episodes saved via Save to Spotify are **personal content** (per Spotify, "can't be shared").
  Still, audio is stored on Spotify's servers and subject to content moderation — don't put
  sensitive information in a briefing.
- For scheduling, `make_briefing.sh` calls the CLI by full path so it works under `cron`/`launchd`
  (which don't load `~/.bash_profile`).
