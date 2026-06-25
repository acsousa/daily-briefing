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

`./install.sh` fetches a set of royalty-free bumper tracks into `briefing/assets/` (optional —
a generated bumper is used if they're absent). Drop your own no-lyric mp3s there to
personalize the rotation. Sources & license: [`briefing/assets/ATTRIBUTION.md`](briefing/assets/ATTRIBUTION.md).

## Setup

```sh
# 1. Get the code
git clone https://github.com/acsousa/daily-briefing.git
cd daily-briefing

# 2. One-shot install — Python venv + deps, ffmpeg, and your .env
./install.sh               # idempotent; prompts for ffmpeg + your Anthropic API key

# 3. Activate the env (now `brief` works without a path prefix)
source .venv/bin/activate

# 4. (optional) Connect Spotify so episodes publish to your show
curl -fsSL https://saveto.spotify.com/install.sh | bash         # install the save-to-spotify CLI
save-to-spotify auth login                                      # one-time browser login
save-to-spotify shows create --title "My Daily Briefing"        # one-time: creates the show, prints its show_uri
#   already have a show? skip create and run `save-to-spotify shows` to copy its show_uri

# 5. Configure in the browser — interests, voices, tone, length. If publishing,
#    paste the show_uri into the SPOTIFY SHOW ID field.
brief config               # opens http://127.0.0.1:8765

# 6. Build today's episode
brief generate             # → briefings/briefing.txt + episode.json
./make_briefing.sh         # render to MP3 (and publish, if Spotify is set up)
```

`./install.sh` is safe to re-run and won't clobber your `.env` or config. If you'd rather do
it by hand, the steps it runs are right there in [`install.sh`](install.sh).

### What's the "Spotify show id"?

Your show is a **one-time creation** — make it once and reuse its id for every episode:

```sh
save-to-spotify shows create --title "My Daily Briefing"   # creates it, prints spotify:show:…
save-to-spotify shows                                      # lists your shows + ids (id is column 1)
```

The id is the **`show_uri`** — a string like `spotify:show:033AAkPmapL99eyKwK0UQO`. Paste the
whole thing (including the `spotify:show:` prefix) into the **SPOTIFY SHOW ID** field in
`brief config`. The id is per **account**, so once created it shows up via `save-to-spotify
shows` on any machine where you've run `auth login` with the same Spotify account (the token
is stored per-machine at `~/.config/save-to-spotify/token.json`). Leave the field blank to skip
publishing — `make_briefing.sh` then just leaves you the MP3 to play in any podcast/news app.

### Running on a remote server (SSH only)

No desktop on the box? The config page and the Spotify login both use a browser, so forward
their ports over SSH from your laptop — **both at once**:

```sh
ssh -L 8765:127.0.0.1:8765 -L 8085:127.0.0.1:8085 you@your-server
```

Then, **inside that same SSH session** on the server:

- **Config page** — `brief config` (it detects the headless box and just prints the URL).
  Open **http://127.0.0.1:8765** in your laptop browser, edit, **Save**, then Ctrl-C.
- **Spotify login** — run `save-to-spotify auth login` in the tunneled session; it completes
  through the tunnel automatically (add `--no-browser` if no browser opens, then open the
  printed URL yourself). Port 8085 is the OAuth callback the tunnel carries back.

(Local 8765 busy? Map another, e.g. `-L 9000:127.0.0.1:8765`, and browse :9000.) Everything
else — `brief generate`, `./make_briefing.sh`, `brief schedule` — runs on the server with no
browser.

### Run it daily (optional)

```sh
brief schedule              # install the daily run
brief schedule --uninstall  # stop the daily run (removes the launchd/systemd/cron job)
```

It builds a fixed **2 hours** before your `drop_time` (set in `brief config`). The mechanism is
chosen for your OS automatically: **launchd** on macOS, a **systemd user timer** on Linux
(or **cron** if systemd isn't available). The machine must be on at that time.

**Stopping things:**
- **Stop the automatic daily run:** `brief schedule --uninstall` (this is how you turn the
  auto-generation off).
- **Stop a foreground command** (`brief config`, `brief generate`, `./make_briefing.sh`):
  press **Ctrl-C** in its terminal.
- **A run launched by the scheduler in the background?** `pkill -f run_daily.sh` (or
  `pkill -f make_briefing` / `pkill -f edge-tts` to interrupt a render).

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
