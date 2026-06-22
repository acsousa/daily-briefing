"""Scriptwriter: render the editor's BEATS into tight two-host news dialogue.

This is a NEWS briefing first, podcast second. Each story is rendered by walking the beats
in order — hook, headline, what happened, why it matters, bridge — so the listener actually
gets the news. Heavy editing: fast back-and-forth, no filler affirmations.

Output is the AVA:/ANDREW: tagged format the renderer consumes; segments are separated by a
[[SEG]] marker.
"""
from __future__ import annotations

from datetime import date

from ..store import EpisodeSegment, SourceAttribution

_SYSTEM = """You write a daily two-host NEWS briefing (AVA anchors, ANDREW analyzes), in the
accessible style of Marketplace. NEWS FIRST, style second: the listener must come away
actually knowing what happened.

Output ONLY dialogue lines, each starting with `AVA:` or `ANDREW:` — one speaker per line.
No stage directions, no markdown, no headers.

Hard rules:
- DELIVER THE NEWS. State the headline plainly, then the concrete facts — who, what, the key
  numbers and names. Do NOT circle the story with analysis while never saying what happened.
- HEAVY EDITING, FAST PACING. This is a briefing, not a podcast chat. Every line advances the
  story. Cut filler — never write a line that is just agreement ("Right.", "Exactly.",
  "Interesting."). If a host speaks, they add a fact, a stake, or a turn.
- Market reactions are a footnote — one short clause at most, never a ticker roll-call.
- Keep fact separate from analysis; frame any forward question as an open question. Invent
  nothing — every claim traces to the provided sources.
Match the requested tone. Stay within the stated word target."""


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
    return int(seconds / 60 * 150)


def _max_tokens(words: int) -> int:
    return max(int(words * 3), 1200)


def write_script(llm, plan, editor_output, clusters_by_id, articles_by_id,
                 fulltext_by_id, profile, weather, today: date):
    tone = profile.get("style", {}).get("tone", "")
    model = llm.script_model
    briefs = {b.story_cluster_id: b for b in editor_output.segments}
    pretty_date = today.strftime("%A, %B %-d")

    parts, episode_segments, briefed = [], [], []
    seen_headline = False

    for seg in plan.segments:
        words = _words_for(seg.allotted_sec)
        mt = _max_tokens(words)
        if seg.kind == "intro":
            owner_name = ((profile.get("owner") or {}).get("name") or "").split()
            first = owner_name[0] if owner_name else ""
            welcome = (f"{first}, welcome to your daily briefing." if first
                       else "Welcome to your daily briefing.")
            user = (f"Tone: {tone}\nThe opening line is already written: 'AVA: {welcome}'. "
                    f"Continue a {words}-word two-host cold open from there — do NOT greet or "
                    "welcome again. Go straight into the day's tension, then preview what's coming "
                    f"in a line or two. It's {pretty_date}. Through-line: "
                    f"\"{editor_output.through_line}\". Brisk, no fabricated details. "
                    "Start your output with an ANDREW line (AVA just spoke the welcome).")
            body = llm.complete(_SYSTEM, user, model=model, max_tokens=mt)
            script, attrs, brk = f"AVA: {welcome}\n{body}", [], False
        elif seg.kind == "weather" and weather:
            user = (f"Tone: {tone}\nWrite at most 2 short lines of two-host weather for "
                    f"{profile.get('owner', {}).get('location', {}).get('city', 'today')}: "
                    f"{weather['conditions']}, high {weather['high_f']}F, low {weather['low_f']}F, "
                    f"{weather['precip_pct']}% precip. Plain and quick. Use only these numbers.")
            script, attrs, brk = llm.complete(_SYSTEM, user, model=model, max_tokens=mt), [], False
        elif seg.kind == "outro":
            user = (f"Tone: {tone}\nWrite a short {words}-word two-host sign-off — concise, a "
                    "touch wry, reinforcing the through-line. No new facts.")
            script, attrs, brk = llm.complete(_SYSTEM, user, model=model, max_tokens=mt), [], True
        else:  # headline
            c = clusters_by_id[seg.story_cluster_id]
            b = briefs.get(c.id)
            is_lead = not seen_headline
            seen_headline = True
            depth = ("LEAD story — give the news room, then a beat of analysis."
                     if is_lead else "QUICK HIT — deliver it fast and move on.")
            beats = ""
            if b:
                beats = (f"Hook: {b.hook}\nHeadline: {b.headline}\n"
                         f"What happened (DELIVER THIS): {b.what_happened}\n"
                         f"Why it matters: {b.why_it_matters}\nBridge: {b.bridge}\n"
                         f"Recap (developing): {b.recap_line}\n")
            user = (
                f"Tone: {tone}\nTarget length: ~{words} words. {depth}\n\n"
                "Render this story by walking the beats IN ORDER — hook, then headline, then "
                "what-happened (state the actual news and numbers), then why-it-matters, then "
                "bridge. Fast two-host exchange, no filler lines.\n\n"
                f"Beats:\n{beats}\n"
                f"Source material (ground every fact in this):\n"
                f"{_sources_block(c, articles_by_id, fulltext_by_id)}\n\n"
                "Write the segment now."
            )
            script = llm.complete(_SYSTEM, user, model=model, max_tokens=mt)
            attrs = _attr(c, articles_by_id)
            brk = True
            briefed.append((c, (b.headline if b else c.title)))

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

    chunks = []
    for i, (text, brk) in enumerate(parts):
        if i > 0:
            chunks.append("\n[[SEG]]\n" if brk else "\n")
        chunks.append(text)
    return "".join(chunks) + "\n", episode_segments, briefed
