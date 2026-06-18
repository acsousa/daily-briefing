"""Scriptwriter (Sonnet): render the editorial brief into grounded two-host dialogue.

Output is the existing ARIA:/ANDREW: tagged format the renderer already consumes, plus
EpisodeSegment records with per-segment source attributions.
"""
from __future__ import annotations

from datetime import date

from ..store import EpisodeSegment, SourceAttribution

_SYSTEM = """You write a two-host audio briefing. ARIA anchors (leads, frames, reads the
through-line); ANDREW is the analyst (connects, questions, the occasional dry aside).

Output ONLY dialogue lines, each starting with `ARIA:` or `ANDREW:` — one speaker per line,
alternating naturally. No stage directions, no markdown, no headers.

Grounding rules (non-negotiable):
- Every factual claim must trace to the provided source text. Do NOT invent quotes, numbers,
  names, or events. If the sources don't support a detail, don't say it.
- Keep fact separate from analysis. Frame the editor's forward-looking question as an open
  question, never as a sourced fact.
- Be the listener's eyes: describe what matters in plain terms.
Match the requested tone. Keep close to the target length."""


def _attr(cluster, articles_by_id):
    return [
        SourceAttribution(article_id=a.id, url=a.url, title=a.title)
        for aid in cluster.article_ids
        if (a := articles_by_id.get(aid))
    ]


def _sources_block(cluster, articles_by_id, fulltext_by_id) -> str:
    parts = []
    for aid in cluster.article_ids:
        a = articles_by_id.get(aid)
        if not a:
            continue
        body = fulltext_by_id.get(aid) or a.summary or ""
        parts.append(f"[{a.source_name}] {a.title}\n{body[:4000]}")
    return "\n\n".join(parts)


def _words_for(seconds: int) -> int:
    return int(seconds / 60 * 165)   # ~165 wpm conversational


def write_script(llm, plan, editor_output, clusters_by_id, articles_by_id,
                 fulltext_by_id, profile, weather, today: date):
    tone = profile.get("style", {}).get("tone", "")
    briefs = {b.story_cluster_id: b for b in editor_output.segments}
    pretty_date = today.strftime("%A, %B %-d")

    texts: list[str] = []
    episode_segments: list[EpisodeSegment] = []
    briefed: list = []                # (cluster, summary) for continuity update

    for seg in plan.segments:
        words = _words_for(seg.allotted_sec)
        if seg.kind == "intro":
            user = (f"Tone: {tone}\nWrite a {words}-word two-host open for the briefing on "
                    f"{pretty_date}. Mention the through-line: \"{editor_output.through_line}\". "
                    "Warm, brief, no fake news details.")
            script = llm.complete(_SYSTEM, user)
            attrs = []
        elif seg.kind == "weather" and weather:
            user = (f"Tone: {tone}\nWrite a {words}-word two-host weather note. "
                    f"Today: {weather['conditions']}, high {weather['high_f']}F, "
                    f"low {weather['low_f']}F, {weather['precip_pct']}% chance of precipitation. "
                    "Only use these numbers.")
            script = llm.complete(_SYSTEM, user)
            attrs = []
        elif seg.kind == "outro":
            user = (f"Tone: {tone}\nWrite a short {words}-word two-host sign-off. "
                    "No new facts.")
            script = llm.complete(_SYSTEM, user)
            attrs = []
        else:  # headline
            c = clusters_by_id[seg.story_cluster_id]
            b = briefs.get(c.id)
            brief_txt = ""
            if b:
                brief_txt = (
                    f"Angle: {b.angle}\nWhy it matters: {b.why_it_matters}\n"
                    f"Connections: {b.connections}\nForward question: {b.forward_question}\n"
                    f"Aside (optional): {b.joke}\nRecap (developing): {b.recap_line}\n"
                )
            user = (
                f"Tone: {tone}\nTarget length: ~{words} words.\n\n"
                f"Editorial brief:\n{brief_txt}\n"
                f"Source material (ground every claim in this):\n"
                f"{_sources_block(c, articles_by_id, fulltext_by_id)}\n\n"
                "Write the two-host segment now."
            )
            script = llm.complete(_SYSTEM, user)
            attrs = _attr(c, articles_by_id)
            briefed.append((c, (b.why_it_matters if b else c.title)))

        texts.append(script.strip())
        episode_segments.append(EpisodeSegment(
            id=f"{plan.id}-{seg.order_index if hasattr(seg, 'order_index') else len(episode_segments)}",
            episode_id=plan.id,
            order_index=len(episode_segments),
            kind=seg.kind,
            story_cluster_id=seg.story_cluster_id,
            script=script.strip(),
            source_attributions=attrs,
        ))

    briefing_text = "\n".join(texts) + "\n"
    return briefing_text, episode_segments, briefed
