"""Editorial pass (Opus): structure each story into news-briefing BEATS.

This is the scaffolding engine. The editor doesn't write prose — it produces a fixed beat
structure per story (hook, headline, what-happened, why-it-matters, bridge, recap) that the
scriptwriter renders into dialogue. News first: `what_happened` must contain the actual,
concrete facts being delivered, not allusions to them.
"""
from __future__ import annotations

import json

from pydantic import BaseModel


class SegmentBrief(BaseModel):
    story_cluster_id: str
    hook: str           # one-line attention grab / tension (≤1 sentence)
    headline: str       # the single edited sentence that STATES the news plainly
    what_happened: str  # 2–4 sentences of the actual news: who/what/when/key numbers
    why_it_matters: str # the stakes in plain terms — real-world consequences
    bridge: str         # one-line transition to the next story OR tie to the through-line
    recap_line: str     # one sentence for a DEVELOPING story; empty string if new


class EditorOutput(BaseModel):
    through_line: str
    segments: list[SegmentBrief]


class TransitionEdit(BaseModel):
    segment_index: int   # which segment (in running order) the fix applies to
    original_excerpt: str  # the exact, verbatim transition text to replace
    corrected_excerpt: str  # the rewritten transition


class TransitionReview(BaseModel):
    edits: list[TransitionEdit]


_SYSTEM = """You are the editor of a daily two-host NEWS briefing. News first, style second —
the listener must come away actually knowing what happened today.

For each story, produce these BEATS (this structure is fixed; the wording is yours):
- hook: a one-line tension or contradiction that earns attention. ≤1 sentence.
- headline: the single, edited sentence that plainly STATES the news (like a wire lede).
- what_happened: 2–4 sentences delivering the ACTUAL news — who, what, when, the key
  numbers and names. This is the substance; it must contain the real facts, not vague
  allusions ("a major development") or pure analysis. Edit it to flow, but deliver it.
- why_it_matters: the stakes in plain terms — concrete consequences for real people/markets.
- bridge: one line that hands off to the next story or ties this to the through-line.
- recap_line: for a DEVELOPING story, one sentence on what was said before; else empty.

Voice: Marketplace — accessible, wry, lightly skeptical, no jargon, never finance-bro.
Market reactions are a footnote, not the focus; never roll-call tickers.
Never invent facts, quotes, or numbers. Honor the user's interests and tone.

through_line: a tension-driven thread that builds in scale across the episode.
Return one brief per story, preserving the given story_cluster_id values."""


def _rundown(plan, clusters_by_id, articles_by_id, decisions) -> str:
    lines = []
    for seg in plan.segments:
        if seg.kind != "headline":
            continue
        c = clusters_by_id[seg.story_cluster_id]
        d = decisions.get(c.id, {})
        facts = []
        for aid in c.article_ids[:5]:
            a = articles_by_id.get(aid)
            if a:
                facts.append(f"{a.title} — {(a.summary or '')[:240]}")
        lines.append(json.dumps({
            "story_cluster_id": c.id,
            "topics": c.topics,
            "sources_covering": c.source_count,
            "status": d.get("status", "new"),
            "prior_recap": d.get("recap") or "",
            "coverage": facts,
        }))
    return "\n".join(lines)


def edit_rundown(llm, plan, clusters_by_id, articles_by_id, decisions, profile) -> EditorOutput:
    style = profile.get("style", {})
    user = (
        f"User interests: {[i['topic'] for i in profile.get('interests', [])]}\n"
        f"Regions of focus: {profile.get('regions', ['U.S.'])}\n"
        f"Tone: {style.get('tone', '')}\n\n"
        "Today's rundown — one JSON story per line, ordered by priority "
        "(sources_covering = how many outlets covered it; higher = bigger news):\n"
        f"{_rundown(plan, clusters_by_id, articles_by_id, decisions)}\n\n"
        "Write the through-line and one beat-brief per story."
    )
    return llm.parse(_SYSTEM, user, EditorOutput, model=llm.editor_model)


_TRANSITION_SYSTEM = """You are the editor doing a final CONTINUITY pass on a two-host news
briefing script. Each segment ends by handing off to whatever comes next; the opening segment
previews what's coming. Your ONLY job is to make every transition factually match the real
running order given to you. The hosts must never:
- tease a topic as "coming up" / "next" / "after this" that is not actually what comes next,
- promise more stories when the show is about to end,
- refer to a story as upcoming when it has already aired,
- sign off before the final segment. Only the final segment (the sign-off) may say goodbye,
  thank the listener, say "that's our briefing" / "see you tomorrow" / "take care", or have
  the hosts introduce themselves in farewell. If any earlier segment does, replace that wording
  with a closing line on the story itself.

You are given the segments in their TRUE running order. Each lists exactly what follows it.
For every segment whose closing handoff — or, for the opening, its preview — misrepresents what
actually comes next, return a surgical edit: the exact verbatim text to replace
(`original_excerpt`, copied character-for-character from that segment, including the AVA:/ANDREW:
prefixes) and the `corrected_excerpt` to put in its place.

Rules:
- Edit ONLY transition / preview wording. Never touch the news facts, numbers, names, or quotes.
- Keep the AVA:/ANDREW: line format and the hosts' wry, brisk voice.
- `original_excerpt` MUST be an exact substring of the named segment, or the edit is dropped.
- If a transition is already accurate, do not return an edit for it.
- Return an empty list if every transition is already correct."""


def _coming_up(idx: int, labels: list[str]) -> str:
    """Describe, for the segment at idx, what genuinely follows it — in order."""
    after = labels[idx + 1:]
    if not after:
        return "NOTHING — this is the final segment; the briefing ends here."
    return " then ".join(f'"{lab}"' for lab in after)


def review_transitions(llm, segments: list[dict], max_passes: int = 2) -> list[dict]:
    """Editorial continuity pass: rewrite any handoff/preview that lies about what's next.

    `segments` is the running order — a list of dicts with `kind`, `label`, and `script`.
    Returns the same list with corrected `script` values. Grounded in the true order, so one
    pass usually suffices; we loop (bounded) until no further edits are returned. Defensive:
    any failure leaves the scripts untouched rather than breaking generation.
    """
    labels = [s["label"] for s in segments]
    for _ in range(max_passes):
        rundown = "\n\n".join(
            f"### SEGMENT {i} ({s['kind']}) — what comes next: {_coming_up(i, labels)}\n{s['script']}"
            for i, s in enumerate(segments)
        )
        user = (
            "Segments in TRUE running order. Fix only transitions that misrepresent what "
            "actually comes next (or that promise more when the show ends), and remove any "
            "goodbye that appears before the final segment:\n\n"
            f"{rundown}"
        )
        try:
            review = llm.parse(_TRANSITION_SYSTEM, user, TransitionReview, model=llm.editor_model)
        except Exception as exc:  # never let the QA step break the pipeline
            print(f"  ! transition review skipped: {exc}")
            return segments
        applied = apply_transition_edits(segments, review.edits)
        if not applied:
            break
    return segments


def apply_transition_edits(segments: list[dict], edits: list[TransitionEdit]) -> int:
    """Apply surgical transition edits in place; skip any whose excerpt isn't found.

    Returns the number of edits actually applied (0 means nothing changed). Replacing only an
    exact substring means a bad/hallucinated excerpt is a safe no-op — it can never corrupt the
    news content of a segment.
    """
    applied = 0
    for e in edits:
        if not (0 <= e.segment_index < len(segments)):
            continue
        seg = segments[e.segment_index]
        excerpt = (e.original_excerpt or "").strip()
        if not excerpt or excerpt not in seg["script"]:
            continue
        seg["script"] = seg["script"].replace(excerpt, e.corrected_excerpt.strip(), 1)
        applied += 1
    return applied
