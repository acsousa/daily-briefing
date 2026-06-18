# Interactive Personal Audio Briefing — Implementation Plan

Build plan for an agent (Claude Code) to take this repo from its current static
two-host briefing prototype to the full **interactive personal audio briefing**
described in the product plan: daily personalized news, commute-length
customization, and live in-audio "dive deeper" conversation with resume.

This plan is grounded in what already exists in this repo — it extends that work
rather than starting over.

---

## 0. Where this repo is today (the v0 baseline)

Already built and working on Andrew's machine:

- `briefing.txt` — two-host script, one line per turn, tagged `ARIA:` / `ANDREW:`.
  Currently sample/practice content.
- `render_briefing.py` — parses turns, renders each with **edge-tts** (Aria +
  Andrew neural voices, `+12%` rate), inserts 0.35s gaps, stitches with **ffmpeg**
  into `briefing-YYYY-MM-DD.mp3`.
- `make_briefing.sh` — renders, then uploads to the **"Andrew's Daily Rundown"**
  show (`spotify:show:033AAkPmapL99eyKwK0UQO`) via the `save-to-spotify` CLI, polls
  until READY. Cron-safe (absolute binary path).
- `save-to-spotify` CLI installed + authenticated; practice episodes published.

**What v0 proves:** the render → stitch → publish pipeline works end to end.
**What v0 lacks:** real content (it's sample text), personalization, length
control, any data model, and any interaction. Everything below builds on this spine.

**Design principle carried from the product plan:** precompute the episode offline;
make only the *interaction layer* live. Do not generate the whole show on-demand.

---

## Phase 1 — Real content pipeline (replace the sample script)

Goal: `briefing.txt` stops being hand-written sample text and becomes the output of
a real ingest → cluster → rank → script pipeline. Keep the existing renderer/uploader
untouched as the final stage.

**1.1 Project skeleton & config**
- Restructure into a package: `briefing/` with `ingest/`, `cluster/`, `rank/`,
  `plan/`, `script/`, `render/`, `publish/`. Move `render_briefing.py` logic into
  `render/`, `make_briefing.sh` becomes the orchestrator (or a Python CLI `brief`).
- Add `config.yaml`: sources, user interest profile, target duration, voices, show id.
- Add `pyproject.toml`, pin deps (edge-tts, feedparser/httpx, pydantic, etc.), `.gitignore`.
- `git init` (repo currently has no git history).

**1.2 Ingestion**
- RSS/Atom + JSON feeds first (cheapest, no keys). Adapter interface so APIs
  (NewsAPI, publisher APIs) can drop in later.
- Normalize to a `RawArticle` model. Dedup by URL/title. Window: last 12–24h.

**1.3 Clustering & ranking (rule-based first)**
- Group articles into `StoryCluster` objects (embeddings + cosine, or title/entity
  overlap to start). One event → one cluster.
- Score clusters: freshness × importance × source quality × interest-profile match ×
  novelty-vs-prior-episodes. Rule-based weights now; learnable later.

**1.4 Episode planner + scripting**
- Planner builds an ordered rundown to fit a **duration budget** (this is the
  commute-length feature — see Phase 2). Segments: intro, weather, headline
  segments, optional deep dives, "day ahead," outro.
- Scripting service writes the two-host dialogue in the **existing `ARIA:`/`ANDREW:`
  tagged format** so `render_briefing.py` consumes it unchanged.
- **Grounding guardrails from day one:** every claim traces to a source snippet;
  no synthesized quotes unless directly sourced; separate fact from analysis;
  attribution captured in metadata.

**1.5 Wire it together**
- `brief generate` produces a real `briefing.txt` + a sidecar `episode.json`
  (segments, source attributions, timings-to-be). Then existing render + upload runs.

**Exit criteria:** a genuinely personalized, real-news episode publishes to the show
with one command, no hand-written script.

---

## Phase 2 — Commute-length customization & structured episode model

Goal: the second pillar of the vision, plus the data model that makes Phase 3 possible.

**2.1 Duration budgeting**
- `--duration 20m|30m|45m` (or per-user default). Planner allocates a time budget per
  segment and selects/depth-adjusts clusters to fit. Estimate audio length from word
  count × speaking rate (calibrate against rendered output).

**2.2 Time-aligned transcript & segment metadata**
- Capture per-turn and per-segment start/end timestamps during render (the renderer
  already produces per-turn clips — record their durations instead of discarding them).
- Emit `EpisodeSegment` records: `segment_id`, `story_cluster_id`, `script`,
  `audio offset`, `start_time`, `end_time`, source attributions.
- **This is the hinge for interactivity:** at any playback timestamp you can resolve
  "what story is playing right now."

**2.3 Persist the object model**
- SQLite to start (zero infra), Postgres + pgvector when it grows. Tables:
  `RawArticle`, `StoryCluster`, `EpisodePlan`, `EpisodeSegment`, `InteractionContext`.

**Exit criteria:** episodes render to a requested length; each episode has a stored,
queryable segment+source model with timecodes.

---

## Phase 3 — Live "dive deeper" interaction layer (the differentiator)

Goal: the third pillar — interrupt playback, ask, get a grounded spoken answer, resume.
Per the plan, **launch grounded only in today's episode sources (Mode A)** for trust.

**3.1 Retrieval prep (precomputed per cluster)**
- For each `StoryCluster`, precompute: 5–15 source snippets, machine summary, timeline,
  named entities, glossary terms, opposing framings, "why it matters," confidence/
  unresolved facts. Store in the knowledge index (pgvector or SQLite + embeddings).

**3.2 Question endpoint (text first, before voice)**
- Service: given `episode_id`, `segment_id`/`timestamp`, and a question → return a
  concise grounded answer + source attributions.
- **Intent router** classifies into: define · more-detail · context · comparison ·
  opposing-views · implications · skip/steer · summarize-last-N-min. Structured intents
  are faster and more reliable than open-ended QA.
- Fallback: "I don't have enough support for that" when grounding is weak.

**3.3 Voice round trip**
- Streaming ASR (question) → intent router → retrieval → LLM answer → streaming TTS.
- Reuse the episode's voice for continuity. Pre-render the show with best-quality TTS;
  answer live with a faster low-latency path in a matching voice.
- Target: answer audio begins in ~1–2s or it feels clunky.

**3.4 Resume / branch logic**
- After the answer, resume from the saved timestamp, or branch into a 90s–3min deep-dive
  extension then return. Track this in `InteractionContext`.

**Exit criteria:** during playback the user can ask a question, hear a grounded spoken
answer in the host voice, and resume — first in a test client, sources Mode A only.

---

## Phase 4 — Client app

Goal: the listening surface. Backend (Phases 1–3) is client-agnostic via a clean API.

- **API layer** (FastAPI): serve episode audio + transcript + timecodes; the live
  question endpoint; user prefs.
- **App:** iOS-first if CarPlay matters early, else React Native for speed. Needs
  background audio, lock-screen/CarPlay controls, mic input, waveform/transcript sync,
  an "Ask" button, and smart prompts ("more context," "opposing views," "why it
  matters," "define term").
- **Source-transparency UI:** "This answer is based on Reuters, FT, and a company
  filing" — a core trust feature.

---

## Phase 5 — V2 differentiation (after the loop works)

- Adaptive mid-playback rewrite ("less sports, more AI").
- Branching deep dives inserted inline.
- Taste learning from expands/skips/replays/questions.
- Multi-voice personas (host / analyst / contrarian / educator).
- Selectively expand to **Mode B** (episode sources + broader corpus) for
  definitions/context, keeping today's-briefing grounding as the default.

---

## Cross-cutting: trust guardrails (build in from Phase 1, not bolted on later)

The product plan's central warning: this category's failure mode is "cool demo,
untrustworthy product." Non-negotiables:

- Source-linked fact grounding; attribution in transcript + UI.
- Recency filters; confidence scoring for breaking news.
- No synthesized quotes unless directly sourced.
- Explicit fact-vs-analysis separation.
- "Not enough support" fallback over confident guessing.

---

## Recommended stack (matches the product plan, sized for a Claude Code build)

- **Now (MVP):** Python + edge-tts + ffmpeg (already in place) · SQLite · local cron.
  Keep infra at zero until the loop is proven.
- **Backend when it grows:** FastAPI · Postgres + pgvector · Redis (cache + live
  session state) · object storage for audio · background jobs (Celery/Temporal/Cloud
  Tasks).
- **Infra MVP:** Cloud Run + Cloud Scheduler + Cloud SQL + Cloud Storage (fewest moving
  parts), or the AWS equivalent.
- **Realtime voice:** streaming ASR + low-latency LLM + streaming TTS.
- **TTS note:** don't use NotebookLM as the production engine — it proves the
  interaction pattern, not a programmable backend. Keep edge-tts for now; evaluate a
  premium TTS (e.g. ElevenLabs) for the production show voice + a fast voice for live
  answers.

---

## Build order (each slice is independently shippable)

1. **Phase 1** — real content into the existing renderer. Biggest value, lowest risk.
2. **Phase 2** — duration control + stored segment/timecode model.
3. **Phase 3.2** — text question endpoint (prove grounding & intent routing).
4. **Phase 3.1/3.3/3.4** — retrieval prep + voice round trip + resume.
5. **Phase 4** — API + client.
6. **Phase 5** — adaptive/branching/personas/Mode B.

Do not skip ahead to live generative radio. Precompute the episode; make the
interaction live. That sequencing is the whole bet.

See `CLAUDE_CODE_PROMPT_PACK.md` for copy-pasteable prompts to execute each slice.
