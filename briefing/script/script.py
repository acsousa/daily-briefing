"""Scriptwriter: render the editor's BEATS into tight two-host news dialogue.

This is a NEWS briefing first, podcast second. Each story is rendered by walking the beats
in order — hook, headline, what happened, why it matters — then a closing handoff, so the
listener actually gets the news. Heavy editing: fast back-and-forth, no filler affirmations.

Transitions are grounded: every segment is written knowing exactly what comes next (or that
the show is ending), and a final editorial continuity pass (see editor.review_transitions)
repairs any handoff that still misrepresents the running order — so the hosts never tease a
topic that isn't actually next, or promise more when the briefing is about to end.

Output is the AVA:/ANDREW: tagged format the renderer consumes; segments are separated by a
[[SEG]] marker.
"""
from __future__ import annotations

from datetime import date

from ..editor import review_transitions
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


def _seg_label(seg, briefs, clusters_by_id) -> str:
    """A short human label for what a segment is about — used to ground transitions."""
    if seg.kind == "intro":
        return "the opening"
    if seg.kind == "weather":
        return "the weather"
    if seg.kind == "outro":
        return "the sign-off"
    c = clusters_by_id[seg.story_cluster_id]
    b = briefs.get(c.id)
    return (b.headline if b and b.headline else c.title)


def _next_up_hint(next_seg, next_label: str | None) -> str:
    """Describe what the current headline must hand off to (or that the show is ending)."""
    if next_seg is None:
        return ("NOTHING comes after this — it is the final story. Wrap toward the sign-off; "
                "do NOT tease another story or say anything is 'coming up next'.")
    if next_seg.kind == "outro":
        # the separate outro owns the goodbye; saying it here too made every episode sign off
        # twice (story goodbye → music bumper → outro goodbye)
        return ("the show's separate sign-off segment — this is the final story. Close the "
                "story itself with a last line of takeaway; do NOT tease another story or "
                "promise more 'after this'. Do NOT sign off: no goodbye, no 'thanks for "
                "listening', no 'that's our briefing', no 'see you tomorrow' or 'take care', "
                "no hosts introducing themselves — the sign-off segment that follows is the "
                "only place the hosts say goodbye.")
    if next_seg.kind == "weather":
        return "a quick weather note. Hand off to the weather, not to another story."
    return (f'the next story: "{next_label}". End with a brief handoff that points to THAT '
            "story specifically — do not name or tease any other topic.")


def write_script(llm, plan, editor_output, clusters_by_id, articles_by_id,
                 fulltext_by_id, profile, weather, today: date):
    tone = profile.get("style", {}).get("tone", "")
    model = llm.script_model
    briefs = {b.story_cluster_id: b for b in editor_output.segments}
    pretty_date = today.strftime("%A, %B %-d")

    # label every segment up front so each one can be written knowing what truly follows it
    seg_labels = [_seg_label(seg, briefs, clusters_by_id) for seg in plan.segments]
    upcoming_stories = [lab for seg, lab in zip(plan.segments, seg_labels)
                        if seg.kind == "headline"]

    rendered, briefed = [], []
    seen_headline = False

    for i, seg in enumerate(plan.segments):
        words = _words_for(seg.allotted_sec)
        mt = _max_tokens(words)
        next_seg = plan.segments[i + 1] if i + 1 < len(plan.segments) else None
        next_label = seg_labels[i + 1] if next_seg is not None else None
        if seg.kind == "intro":
            owner_name = ((profile.get("owner") or {}).get("name") or "").split()
            first = owner_name[0] if owner_name else ""
            welcome = (f"{first}, welcome to your daily briefing." if first
                       else "Welcome to your daily briefing.")
            preview = "; ".join(upcoming_stories) or "today's stories"
            user = (f"Tone: {tone}\nThe opening line is already written: 'AVA: {welcome}'. "
                    f"Continue a {words}-word two-host cold open from there — do NOT greet or "
                    "welcome again. Go straight into the day's tension, then briefly preview "
                    f"what's coming. It's {pretty_date}. Through-line: "
                    f"\"{editor_output.through_line}\".\n\n"
                    "Today's stories, in the exact order they will air:\n"
                    f"{preview}\n\n"
                    "Tease only the biggest two or three of these, and only in this order. Do NOT "
                    "mention any topic that is not in this list, and do not imply a different "
                    "order. Brisk, no fabricated details. "
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
                    "touch wry, reinforcing the through-line. The briefing is ending: do NOT "
                    "tease or promise any further story. No new facts. This is the ONLY goodbye "
                    "in the episode — the last story ended without one — so sign off here, "
                    "once.")
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
                         f"Why it matters: {b.why_it_matters}\n"
                         f"Recap (developing): {b.recap_line}\n")
            user = (
                f"Tone: {tone}\nTarget length: ~{words} words. {depth}\n\n"
                "Render this story by walking the beats IN ORDER — hook, then headline, then "
                "what-happened (state the actual news and numbers), then why-it-matters, then a "
                "closing handoff. Fast two-host exchange, no filler lines.\n\n"
                f"Beats:\n{beats}\n"
                f"What comes next: {_next_up_hint(next_seg, next_label)}\n\n"
                f"Source material (ground every fact in this):\n"
                f"{_sources_block(c, articles_by_id, fulltext_by_id)}\n\n"
                "Write the segment now."
            )
            script = llm.complete(_SYSTEM, user, model=model, max_tokens=mt)
            attrs = _attr(c, articles_by_id)
            brk = True
            briefed.append((c, (b.headline if b else c.title)))

        rendered.append({
            "kind": seg.kind,
            "label": seg_labels[i],
            "script": script.strip(),
            "story_cluster_id": seg.story_cluster_id,
            "attrs": attrs,
            "brk": brk,
        })

    # editorial continuity pass: fix any handoff/preview that misrepresents the real running order
    rendered = review_transitions(llm, rendered)

    episode_segments = [
        EpisodeSegment(
            id=f"{plan.id}-{idx}",
            episode_id=plan.id,
            order_index=idx,
            kind=r["kind"],
            story_cluster_id=r["story_cluster_id"],
            script=r["script"],
            source_attributions=r["attrs"],
        )
        for idx, r in enumerate(rendered)
    ]

    chunks = []
    for i, r in enumerate(rendered):
        if i > 0:
            chunks.append("\n[[SEG]]\n" if r["brk"] else "\n")
        chunks.append(r["script"])
    return "".join(chunks) + "\n", episode_segments, briefed
