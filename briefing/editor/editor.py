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
