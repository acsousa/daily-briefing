# Claude Code Prompt Pack — Interactive Briefing Build

Copy-pasteable prompts to drive the build in `IMPLEMENTATION_PLAN.md`, slice by slice.
Run these from inside Claude Code in this repo (`projects/podcasting`). Do each slice,
review the diff, commit, then move to the next. Don't paste them all at once.

**Context to give Claude Code once at the start of a session:**

> Read IMPLEMENTATION_PLAN.md and the existing files (briefing.txt, render_briefing.py,
> make_briefing.sh). We are extending this working v0 pipeline, not replacing it. The
> renderer's `ARIA:`/`ANDREW:` tagged script format and the save-to-spotify upload step
> must keep working. Precompute episodes offline; only the interaction layer is live.
> Build in trust guardrails (source grounding, attribution, no synthesized quotes) from
> the start. Work one slice at a time, write tests, and stop for review before moving on.

---

## Slice 0 — Initialize repo & guardrails

> Initialize git in this repo. Add a `.gitignore` for Python, audio artifacts
> (`briefing-*.mp3`, `practice-*.mp3`), `.env`, and `__pycache__`. Add a `pyproject.toml`
> with deps: edge-tts, httpx, feedparser, pydantic, pyyaml, pytest. Create a `briefing/`
> package with empty submodules: ingest, cluster, rank, plan, script, render, publish,
> store. Move the logic from render_briefing.py into briefing/render/ as a module, keeping
> a thin render_briefing.py shim so make_briefing.sh still works. Add a `config.yaml`
> with: sources (empty list for now), interest_profile, target_duration_minutes: 20,
> voices (ARIA/ANDREW), show_id (spotify:show:033AAkPmapL99eyKwK0UQO). Commit.

## Slice 1 — Data models

> In briefing/store/, define pydantic models from IMPLEMENTATION_PLAN.md: RawArticle,
> StoryCluster, EpisodePlan, EpisodeSegment, InteractionContext. Add a SQLite persistence
> layer (one table per model, JSON columns where convenient). Write pytest tests that
> round-trip each model through the store. Commit.

## Slice 2 — Ingestion

> Build briefing/ingest/: an RSS/Atom + JSON-feed adapter behind a `SourceAdapter`
> interface, reading the source list from config.yaml. Fetch the last 24h, normalize to
> RawArticle, dedupe by URL and near-duplicate title. Add 2–3 real default feeds to
> config.yaml. Add a `brief ingest` CLI command that fetches and stores articles. Write
> tests with recorded/fixture feeds (no live network in tests). Commit.

## Slice 3 — Clustering & ranking

> Build briefing/cluster/ to group RawArticles into StoryClusters (start with title +
> entity overlap; leave a hook for embedding similarity). Build briefing/rank/ to score
> clusters by freshness, importance, source quality, interest-profile match, and novelty
> vs the prior episode, with weights in config.yaml. Add `brief cluster` and `brief rank`
> CLI commands. Tests on fixture article sets. Commit.

## Slice 4 — Planner + scripting (real briefing.txt)

> Build briefing/plan/ to produce an EpisodePlan: ordered segments (intro, weather,
> headline segments, optional deep dives, day-ahead, outro) fit to
> target_duration_minutes via a per-segment time budget (estimate length from word count
> × speaking rate). Build briefing/script/ to write two-host dialogue in the EXISTING
> `ARIA:`/`ANDREW:` tagged format, one cluster per segment, every claim traceable to a
> source snippet — NO synthesized quotes unless directly sourced, keep fact and analysis
> separate, and record source attributions per segment in episode.json. Add `brief
> generate` that runs ingest→cluster→rank→plan→script and writes briefing.txt +
> episode.json. Then the existing render + upload still runs unchanged. Commit.

## Slice 5 — Duration control + timecodes

> Add `--duration 20m|30m|45m` to `brief generate`, flowing into the planner's budget.
> Modify the renderer to record each turn's and segment's real duration and write
> start/end timestamps into EpisodeSegment records (it already renders per-turn clips —
> capture their lengths instead of discarding them). After render, persist the episode's
> segments with timecodes and source attributions. Add a test that asserts total audio
> length is within tolerance of the requested duration. Commit.

## Slice 6 — Retrieval prep

> Build briefing/store retrieval prep: for each StoryCluster precompute 5–15 source
> snippets, a machine summary, timeline, named entities, glossary terms, opposing
> framings, "why it matters," and a confidence/unresolved-facts note. Store embeddings
> (sqlite + a local embedding model, or pgvector when migrated). Add `brief index` to
> build this for the latest episode. Tests on a fixture cluster. Commit.

## Slice 7 — Question endpoint (text first)

> Build a FastAPI service with POST /ask taking {episode_id, segment_id or timestamp,
> question}. Resolve the playing segment from timecodes, run an intent router (define ·
> more-detail · context · comparison · opposing-views · implications · skip/steer ·
> summarize-last-N-min), retrieve from THIS EPISODE'S sources only (Mode A), and return a
> concise grounded answer + source attributions. Return an explicit "not enough support"
> response when grounding is weak. Tests covering each intent and the fallback. Commit.

## Slice 8 — Voice round trip + resume

> Add streaming ASR for the question and streaming TTS for the answer in a voice matching
> the host, targeting first-audio in ~1–2s. Add resume logic: after answering, resume
> from the saved timestamp, or branch into a short (90s–3min) deep-dive extension then
> return, tracking state in InteractionContext. Provide a minimal CLI/web test harness
> that plays an episode, lets you interrupt with a question, and resumes. Commit.

## Slice 9 — API + client (separate effort)

> Expose serving endpoints: GET episode audio + transcript + timecodes, the /ask
> endpoint, and user prefs. Then scaffold the client (iOS-first if CarPlay matters, else
> React Native): background audio, lock-screen/CarPlay controls, mic, waveform/transcript
> sync, an Ask button with smart-prompt chips, and a source-transparency panel showing
> which sources grounded each answer.

---

## Working agreement for the agent

- One slice per session; show the diff and stop for review before committing the next.
- Never break the `ARIA:`/`ANDREW:` format or the save-to-spotify upload step.
- Keep infra at zero (SQLite, local cron) until the full loop works; migrate to
  Postgres/pgvector/Cloud Run only when scale demands it.
- Trust first: if a claim isn't grounded in a source, it doesn't go in the script or the
  answer.
