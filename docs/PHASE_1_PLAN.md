# Phase 1 — Real Content Pipeline (detailed plan)

Extends the working v0 (render → stitch → publish) into a personalized, real-news
briefing. The renderer's `ARIA:`/`ANDREW:` format and the `save-to-spotify` upload step
stay unchanged as the final stage. Guiding bet: **precompute the episode offline; make
only the interaction layer live.**

## Design decisions

1. **Personal vs operational config, split for open source.**
   - `profile.yaml` — *the user*: interest topics + weights, locale, style brief, host
     personas, must-cover/avoid. Feeds ranking + scripting.
   - `config.yaml` — *the system*: source feeds, ingest window, weather location, voices,
     show id, render settings.
   - Both are **gitignored**; the repo ships `profile.example.yaml` / `config.example.yaml`
     with generic defaults. The loader prefers the personal file, falls back to the example,
     so a fresh clone runs out of the box. **No personal interests/feeds hardcoded in code.**
2. **Content access = the user's own reading.** The tool fetches and summarizes full
   article text the user could read online — not just titles. Accuracy guardrails (source
   attribution, grounding, no fabricated quotes) stay; they're about correctness, not access.
   Because output is published to Spotify and the repo is open source, briefings are
   **synthesis in the hosts' own words**, not verbatim reproduction of copyrighted passages.
3. **Persistence:** SQLite, one table per model. Promote queried columns (ids, dates,
   status, foreign keys, content_hash); store the full model as a `data` JSON column.
4. **Deps minimal:** `difflib` for near-dup titles before reaching for `rapidfuzz`;
   Open-Meteo (no API key) for weather.
5. **Deploy:** runs unattended each morning on a separate always-on machine (scheduler
   chosen once the target OS is known — cron/systemd/container; **no launchd**). Code stays
   container-friendly (config via files/env, absolute paths, no interactive prompts) so a
   `Dockerfile` can be added as a later slice before that move.

## Package layout

```
briefing/
  config.py            # load + merge profile.yaml / config.yaml (with .example fallback)
  store/{models,db}.py # 5 pydantic models + SQLite Store
  ingest/{base,feeds,dedupe}.py
  cluster/ rank/ plan/ script/ render/ publish/   # filled in later slices
config.example.yaml  profile.example.yaml         # committed (generic)
config.yaml          profile.yaml                 # gitignored (personal)
```

## Data models (`store/models.py`)

- **RawArticle** — `id`, `url`, `canonical_url`, `title`, `summary`, `content?`, `author?`,
  `source_id`, `source_name`, `topics`, `published_at`, `fetched_at`, `content_hash`,
  `language?`, `raw: dict`.
- **StoryCluster** — `id`, `title`, `summary?`, `article_ids`, `topics`, `entities`,
  `first_seen`, `last_updated`, `score?`, `score_components: dict`.
- **EpisodePlan** — `id`, `date`, `target_duration_sec`, `segments` (cluster_id + kind +
  allotted_sec), `status`, `show_id`, `created_at`.
- **EpisodeSegment** — `id`, `episode_id`, `order_index`, `kind`, `story_cluster_id?`,
  `script`, `source_attributions`, `audio_offset_sec?`, `start_time?`, `end_time?`.
- **InteractionContext** — `id`, `episode_id`, `segment_id?`, `timestamp_sec`, `question`,
  `intent?`, `answer?`, `answer_sources`, `created_at` (Phase 3, table defined now).

## Ingestion (`ingest/`)

- `SourceAdapter` ABC: `source_id`, `source_name`, `fetch(since) -> list[RawArticle]`.
  HTTP fetch is **injectable** so tests use fixtures — no live network in tests.
- `FeedAdapter`: RSS/Atom (feedparser) + JSON Feed (httpx). Normalizes entries → RawArticle.
- Window: keep entries published within `window_hours` (default 24).
- Dedupe: canonicalize URL (drop `utm_*`, fragments) for exact dupes; near-dup titles via
  normalized `difflib.SequenceMatcher` ratio > ~0.85.
- `brief ingest` CLI: run all adapters, dedupe, store, print per-source summary.

## Content sourcing map (default feeds, validated live during Slice 2)

Big tech · defense/natsec · robotics · economy/finance · local Boston · world · science
kicker — curated free RSS/JSON, full-text fetched and synthesized with attribution.
Weather via Open-Meteo. Paywalled outlets: use what's accessible, attribute, never
reproduce full copyrighted bodies in published audio.

## Build order (each independently shippable, committed)

- **Slice 0** — package skeleton, `pyproject.toml`, example+personal configs, config loader,
  render logic relocated into `briefing/render/` behind a thin `render_briefing.py` shim.
- **Slice 1** — models + SQLite store + round-trip tests.
- **Slice 2** — ingest adapters + dedupe + default feeds + `brief ingest` + fixture tests.
- Later: clustering (1.3), ranking off `profile.yaml` weights (1.3), planner + scripting
  (1.4–1.5), weather adapter; then a Dockerfile slice before moving to the deploy machine.

Trust guardrails are built in from Slice 4 scripting, not bolted on: every claim traces to
a source, no synthesized quotes, fact vs analysis separated, attribution recorded per segment.
