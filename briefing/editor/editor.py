"""Editorial pass (Opus): turn the ranked, continuity-aware rundown into an editorial
brief — cross-discipline connections, why-it-matters, forward-looking questions, sparing
wit — that the scriptwriter renders as dialogue. This is the show's voice."""
from __future__ import annotations

import json

from pydantic import BaseModel, Field


class SegmentBrief(BaseModel):
    story_cluster_id: str
    angle: str                       # the take/framing for this story
    why_it_matters: str              # plain-terms significance
    connections: list[str]           # ties to other segments / disciplines (may be empty)
    forward_question: str            # "where is this headed?" (empty string if none)
    joke: str                        # optional dry aside (empty string if none)
    recap_line: str                  # one-line callback for a developing story (empty if new)


class EditorOutput(BaseModel):
    through_line: str                # the day's connective thread
    segments: list[SegmentBrief]


_SYSTEM = """You are the editor of a daily two-host audio briefing — the role that makes it
worth listening to rather than a feed reader. Inspired by the accessible-context style of
Marketplace (clarity without jargon), the brevity of Morning Brew, and the serious analysis
of War on the Rocks when warranted.

Your job: given today's ranked stories, produce an editorial brief per story plus one
connective through-line for the episode. For each story:
- angle: the sharpest framing — ideally a TENSION or CONTRADICTION that pulls the listener
  in (e.g. "retail sales are up, but households aren't spending from strength"). The angle
  should promise to explain the hidden mechanism underneath the headline number.
- why_it_matters: significance translated into EVERYDAY CONSEQUENCES — concrete decisions and
  lives (who hires, who buys, who waits), not abstract metrics. Plain language, no jargon,
  but keep the core fact/number visible.
- connections: name real ties across stories/disciplines when they exist (e.g. a chip rule
  touching tech + defense + markets). Empty list if there is no honest connection.
- forward_question: the intelligent "where is this headed?" question. It is a QUESTION, not
  a claim — never assert an unsourced prediction. Empty string if none fits.
- joke: at most one dry, earned aside — wry and lightly skeptical, never finance-bro, never
  judgmental of people. A familiar phrase with a twist works well. Empty string if nothing
  lands. Never force it.
- recap_line: for a DEVELOPING story, one sentence on what was said before so today builds
  on it instead of repeating. Empty string for a new story.

Voice (Marketplace, Kai Ryssdal): conversational business journalism, not finance-bro
analysis. Translate indicators into how they land in real life. Wry, lightly skeptical,
accessible to a smart non-specialist.

Focus on SUBSTANCE, not market mechanics — what happened and its stakes, not stock-price
reactions. For a markets/movers story, pick the one or two genuinely meaningful developments
and say why they matter; never roll-call tickers and percentages.

through_line: a tension-driven thread that builds in SCALE across the episode — from concrete
and personal toward systemic and global — so the show gains altitude as it goes.

The first story in the rundown is the LEAD — give it the richest angle. The rest are quick
hits: a sharp angle and a tight why_it_matters, no sprawling connections.

Hard rules: connections and questions are analysis, kept distinct from sourced fact. Never
invent quotes, numbers, or events. Honor the user's interests and tone.
Return one segment brief per story, preserving the given story_cluster_id values."""


def _rundown(plan, clusters_by_id, articles_by_id, decisions) -> str:
    lines = []
    for seg in plan.segments:
        if seg.kind != "headline":
            continue
        c = clusters_by_id[seg.story_cluster_id]
        d = decisions.get(c.id, {})
        headlines = [articles_by_id[aid].title for aid in c.article_ids if aid in articles_by_id]
        lines.append(json.dumps({
            "story_cluster_id": c.id,
            "title": c.title,
            "topics": c.topics,
            "status": d.get("status", "new"),
            "prior_recap": d.get("recap") or "",
            "headlines": headlines[:6],
        }))
    return "\n".join(lines)


def edit_rundown(llm, plan, clusters_by_id, articles_by_id, decisions, profile) -> EditorOutput:
    style = profile.get("style", {})
    user = (
        f"User interests: {[i['topic'] for i in profile.get('interests', [])]}\n"
        f"Tone: {style.get('tone', '')}\n"
        f"Inspirations: {style.get('inspirations', [])}\n\n"
        "Today's rundown (one JSON story per line):\n"
        f"{_rundown(plan, clusters_by_id, articles_by_id, decisions)}\n\n"
        "Write the through-line and one brief per story."
    )
    return llm.parse(_SYSTEM, user, EditorOutput, model=llm.editor_model)
