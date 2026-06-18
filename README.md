# Daily Briefing → Spotify

A small pipeline that turns a written daily briefing into a **two-host audio episode**
and saves it to Spotify as a private podcast episode using Spotify's official
[`save-to-spotify`](https://github.com/spotify/save-to-spotify) CLI.

```
briefings/briefing.txt
   → render_briefing.py  (edge-tts renders each host's lines, ffmpeg stitches them)
   → briefings/briefing-YYYY-MM-DD.mp3
   → make_briefing.sh    (uploads to the "Andrew's Daily Rundown" show, polls until READY)
```

This is the **v0 baseline**: the render → stitch → publish loop works end to end with a
hand-written sample script. See [the roadmap](#roadmap) for where it's headed.

## Repository layout

```
.
├── render_briefing.py          # two-voice render + stitch → dated MP3
├── make_briefing.sh            # full pipeline: render → upload → poll READY
├── briefings/
│   ├── briefing.txt            # the day's script (ARIA: / ANDREW: tagged lines)
│   └── briefing-YYYY-MM-DD.mp3 # rendered episodes (git-ignored)
└── docs/
    ├── README.md               # this file
    ├── IMPLEMENTATION_PLAN.md  # phased plan to the interactive briefing product
    ├── CLAUDE_CODE_PROMPT_PACK.md  # copy-paste prompts to drive each build slice
    └── SAVE_TO_SPOTIFY_SETUP.md    # CLI install + auth handoff notes
```

| Component | Purpose |
|-----------|---------|
| `briefings/briefing.txt` | The day's script. One line per turn, tagged `ARIA:` / `ANDREW:`. |
| `render_briefing.py` | Renders both voices (edge-tts) at `+12%` tempo, inserts 0.35s gaps, stitches to a dated MP3 (ffmpeg). Config — voices, rate, gap — is at the top of the file. |
| `make_briefing.sh` | Full pipeline: render → upload to the show → poll until the episode is `READY`. |

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

### Generate a real briefing (Phase 1 pipeline)

```sh
pip install -e ".[dev]"            # installs the briefing package + deps
brief generate                     # ingest → cluster → rank → plan → edit → script
./make_briefing.sh                 # render + upload the generated briefings/briefing.txt
```

`brief generate` reads your `profile.yaml` (interests, style) and `config.yaml` (feeds,
target duration, voices) and writes `briefings/briefing.txt` + `briefings/episode.json`.
Useful flags:

```sh
brief generate --dry-run           # ingest + plan only; prints the rundown, no LLM calls
brief generate --minutes 25        # override target duration
brief ingest                       # just fetch + filter + store articles
```

The editor and scriptwriter stages call the Claude API, so set `ANTHROPIC_API_KEY` in a
gitignored `.env` (or your shell). `--dry-run` needs no key. Models are configured under
`llm:` in `config.yaml` (editor → Opus, scripting → Sonnet by default).

### Hand-written briefing (still supported)

Edit `briefings/briefing.txt` directly (keep the `ARIA:` / `ANDREW:` tags), then:
```sh
./make_briefing.sh                 # render + upload
python3 render_briefing.py         # render only → briefings/briefing-YYYY-MM-DD.mp3
```

## Roadmap

The current pipeline is the v0 spine. The plan
([`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)) extends it toward an
interactive personal audio briefing, one independently shippable slice at a time.
Guiding bet: **precompute the episode offline; make only the interaction layer live.**

1. **Phase 1 — Real content.** Replace the hand-written script with an ingest → cluster →
   rank → plan → script pipeline producing a personalized, real-news `briefing.txt`. The
   renderer/uploader stay unchanged as the final stage.
2. **Phase 2 — Length control + data model.** Commute-length budgeting (`20m/30m/45m`) and
   a stored, timecoded segment/source model per episode.
3. **Phase 3 — Live "dive deeper."** Interrupt playback, ask a question, get a grounded
   spoken answer from the episode's sources, then resume.
4. **Phase 4 — Client app.** API + listening surface (background audio, CarPlay, "Ask"
   button, source-transparency UI).
5. **Phase 5 — Adaptive V2.** Mid-playback rewrite, branching deep dives, taste learning,
   multi-voice personas.

**Trust guardrails are built in from Phase 1, not bolted on:** source-linked fact
grounding with attribution, recency/confidence filters, no synthesized quotes, explicit
fact-vs-analysis separation, and a "not enough support" fallback over confident guessing.

## Notes

- Generated `.mp3` files are git-ignored — they're build artifacts.
- Episodes saved via Save to Spotify are **personal content** (per Spotify, "can't be shared").
  Still, audio is stored on Spotify's servers and subject to content moderation — don't put
  sensitive information in a briefing.
- For scheduling, `make_briefing.sh` calls the CLI by full path so it works under `cron`/`launchd`
  (which don't load `~/.bash_profile`).
