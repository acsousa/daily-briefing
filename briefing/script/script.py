"""Scriptwriter: render the editorial brief into grounded two-host dialogue.

Output is the existing ARIA:/ANDREW: tagged format the renderer consumes. Segments are
separated by a blank line so the renderer inserts a longer pause + sting between them.
"""
from __future__ import annotations

from datetime import date

from ..store import EpisodeSegment, SourceAttribution

_SYSTEM = """You write a two-host audio briefing. ARIA anchors (leads, frames, reads the
through-line); ANDREW is the analyst (connects, questions, the occasional dry aside).

Output ONLY dialogue lines, each starting with `ARIA:` or `ANDREW:` — one speaker per line,
alternating naturally. No stage directions, no markdown, no headers.

What makes it good (read carefully):
- Lead with WHAT HAPPENED and WHY IT MATTERS — the substance of the story, its stakes, the
  people and decisions involved. That is the spine of every segment.
- Market reaction is a passing NOTE, not the focus. Do NOT roll through tickers and
  percentages. If a price move matters, mention it in one short clause and move on. Never
  let a segment become a list of stock moves.
- Begin each story with a brief, natural verbal hand-off from the previous topic (one line).
- Keep fact separate from analysis; frame forward-looking questions as open questions, never
  as sourced fact. Invent nothing — every claim traces to the provided sources.

Length discipline is REQUIRED. Stay within the stated word target. Quick-hit segments must
stay tight — make the point and get out; do not over-explain or go deep on secondary detail.
Match the requested tone."""


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
    return int(seconds / 60 * 150)   # ~150 wpm at the slower pace


def _max_tokens(words: int) -> int:
    # generous headroom so a segment never truncates mid-sentence (~1.4 tokens/word)
    return max(int(words * 3), 1200)


def write_script(llm, plan, editor_output, clusters_by_id, articles_by_id,
                 fulltext_by_id, profile, weather, today: date):
    tone = profile.get("style", {}).get("tone", "")
    model = llm.script_model
    briefs = {b.story_cluster_id: b for b in editor_output.segments}
    pretty_date = today.strftime("%A, %B %-d")

    parts = []                        # (text, break_before)
    episode_segments: list[EpisodeSegment] = []
    briefed: list = []
    seen_headline = False

    for seg in plan.segments:
        words = _words_for(seg.allotted_sec)
        if seg.kind == "intro":
            user = (f"Tone: {tone}\nWrite a {words}-word two-host open for {pretty_date}. "
                    f"Set up the day's through-line: \"{editor_output.through_line}\". "
                    "Warm, brief, no fabricated details.")
            script, attrs, brk = llm.complete(_SYSTEM, user, model=model, max_tokens=_max_tokens(words)), [], False
        elif seg.kind == "weather" and weather:
            user = (f"Tone: {tone}\nWrite at most 2 short lines of two-host weather for "
                    f"{profile.get('owner', {}).get('location', {}).get('city', 'today')}: "
                    f"{weather['conditions']}, high {weather['high_f']}F, low {weather['low_f']}F, "
                    f"{weather['precip_pct']}% precip. Plain and quick — no flowery description. "
                    "Use only these numbers.")
            script, attrs, brk = llm.complete(_SYSTEM, user, model=model, max_tokens=_max_tokens(words)), [], False
        elif seg.kind == "outro":
            user = f"Tone: {tone}\nWrite a short {words}-word two-host sign-off. No new facts."
            script, attrs, brk = llm.complete(_SYSTEM, user, model=model, max_tokens=_max_tokens(words)), [], True
        else:  # headline
            c = clusters_by_id[seg.story_cluster_id]
            b = briefs.get(c.id)
            is_lead = not seen_headline
            seen_headline = True
            depth = ("This is the LEAD story — give it room for real analysis."
                     if is_lead else
                     "This is a QUICK HIT — tight and punchy, one clear point, then move on.")
            brief_txt = ""
            if b:
                brief_txt = (f"Angle: {b.angle}\nWhy it matters: {b.why_it_matters}\n"
                             f"Connections: {b.connections}\nForward question: {b.forward_question}\n"
                             f"Aside (optional): {b.joke}\nRecap (developing): {b.recap_line}\n")
            user = (f"Tone: {tone}\nTarget length: ~{words} words. {depth}\n\n"
                    f"Editorial brief:\n{brief_txt}\n"
                    f"Source material (ground every claim in this; focus on the substance, "
                    f"not market moves):\n{_sources_block(c, articles_by_id, fulltext_by_id)}\n\n"
                    "Write the two-host segment now, opening with a one-line hand-off.")
            script = llm.complete(_SYSTEM, user, model=model, max_tokens=_max_tokens(words))
            attrs = _attr(c, articles_by_id)
            brk = True
            briefed.append((c, (b.why_it_matters if b else c.title)))

        parts.append((script.strip(), brk))
        episode_segments.append(EpisodeSegment(
            id=f"{plan.id}-{len(episode_segments)}",
            episode_id=plan.id,
            order_index=len(episode_segments),
            kind=seg.kind,
            story_cluster_id=seg.story_cluster_id,
            script=script.strip(),
            source_attributions=attrs,
        ))

    # assemble: an explicit [[SEG]] marker before break segments (the renderer puts a
    # longer pause + sting there). Plain newline where segments should flow together.
    # A sentinel is used rather than a blank line because the model double-spaces turns.
    chunks = []
    for i, (text, brk) in enumerate(parts):
        if i > 0:
            chunks.append("\n[[SEG]]\n" if brk else "\n")
        chunks.append(text)
    briefing_text = "".join(chunks) + "\n"
    return briefing_text, episode_segments, briefed
