"""
story_assembler.py — Phase 3: Assemble the final story.

Two sub-components:
  1. FluentNarrator   — takes raw plot points and expands them into polished prose.
  2. RevelationWriter — generates the detective's final explanation scene.

Key fixes vs. original:
  - Narrates ALL plot points in ONE call instead of batches → no restarts/duplication
  - max_output_tokens raised to 8192 for narration, 4096 for revelation → no truncation
  - NoneType guard: if response.text is None, retry with fresh call before falling back
  - "story so far" context passed to revelation is the full narrative (not just 500 chars)
  - Revelation token budget raised to 4096 so it doesn't cut off mid-sentence
"""

from __future__ import annotations
from typing import Any

from llm_client import call_llm
from config import NARRATOR_MODEL, PROSE_TEMPERATURE


# ─── System instructions ──────────────────────────────────────────────────────

NARRATOR_SYSTEM = """\
You are a literary crime fiction author in the tradition of Agatha Christie \
and Tana French. Your prose is atmospheric, precise, and psychologically acute. \
You expand a numbered list of raw plot-point summaries into one continuous, \
fully realized narrative — third-person limited from the detective's point of view. \
The output is a SINGLE UNBROKEN story from first plot point to last. \
Do NOT restart the story, do NOT re-introduce the detective more than once, \
do NOT repeat scene-setting. Maintain suspense throughout. \
NEVER reveal the killer's identity before the final revelation scene.
"""

REVELATION_SYSTEM = """\
You are writing the climactic revelation scene of a crime mystery novel. \
The detective gathers all suspects and walks through the hidden truth of what \
happened, step by step, revealing how the crime was committed and who did it. \
This scene should be dramatically satisfying, tying every clue and red herring \
back to the truth. Write in vivid, literary third-person prose. \
Write at least 500 words. Do NOT stop mid-sentence. Complete the full scene \
including the culprit's arrest or confession before you stop.
"""


# ─── Fluent Narrator ─────────────────────────────────────────────────────────

def narrate_plot_points(
    plot_points: list[str],
    state: dict[str, Any],
) -> str:
    """
    Expand ALL raw plot points into one continuous narrative in a single LLM call.

    One call avoids the restart/duplication problem that batching caused.
    8192 tokens is enough for 18 plot points at ~2-3 paragraphs each.
    """
    print("\n✍️   Phase 3a — Fluent narration (single call)…", end=" ", flush=True)

    detective_name = _get_detective_name(state)
    victim_name    = state["victim"]["name"]
    setting        = state["setting"]["location"]
    date_          = state["setting"]["date"]

    numbered = "\n".join(f"{i+1}. {pp}" for i, pp in enumerate(plot_points))

    prompt = f"""\
You are writing a complete crime mystery investigation story.

Setting: {setting}
Date: {date_}
Victim: {victim_name}
Detective: {detective_name}

Below are {len(plot_points)} plot points in order. Expand them into ONE continuous, \
unbroken third-person narrative. Each plot point should become 1–3 paragraphs. \
Do NOT number the paragraphs. Do NOT restart the story partway through. \
Introduce the detective only ONCE at the very beginning. \
Transition smoothly between every plot point. \
Do NOT reveal who the killer is — that comes in a separate scene afterward. \
Write until you have covered every single plot point below.

PLOT POINTS:
{numbered}
"""

    result = _safe_call_llm(
        prompt=prompt,
        model_name=NARRATOR_MODEL,
        system_instruction=NARRATOR_SYSTEM,
        max_output_tokens=8192,
    )

    if result:
        print("✓")
        return result.strip()
    else:
        print("✗ (LLM returned empty — using raw plot points)")
        return "\n\n".join(plot_points)


# ─── Revelation Scene Writer ──────────────────────────────────────────────────

def write_revelation_scene(
    state: dict[str, Any],
    story_so_far: str,
) -> str:
    """
    Generate the detective's final revelation scene.

    Passes the FULL crime world state (ground truth) so the LLM has everything
    it needs to tie every clue and red herring back to the truth.
    """
    print("    Writing revelation scene…", end=" ", flush=True)

    culprit   = state["culprit"]
    victim    = state["victim"]
    clues     = state["clues"]
    suspects  = state["suspects"]
    backstory = state.get("hidden_backstory", "")

    clue_summary = "\n".join(
        f"  - [{c['id']}] {c['description']}"
        + (" ← RED HERRING: " + c["red_herring_explanation"] if c.get("is_red_herring") else "")
        for c in clues
    )

    suspect_summary = "\n".join(
        f"  - {s['name']} ({s['occupation']}): missing {s['missing_element']}, "
        f"alibi={s['alibi']}"
        for s in suspects
    )

    # Give the revelation writer the last ~2000 chars of story for context
    story_tail = story_so_far[-2000:] if len(story_so_far) > 2000 else story_so_far

    prompt = f"""\
You are writing the COMPLETE final revelation scene of a murder mystery. \
Write at least 500 words. Do not stop until the scene is fully finished \
— including the culprit's arrest or confession.

=== HIDDEN GROUND TRUTH (now to be revealed) ===
Victim: {victim['name']} — {victim['background']}
Culprit: {culprit['name']}
  - Means: {culprit['means']}
  - Motive: {culprit['motive']}
  - Opportunity: {culprit['opportunity']}
  - Method: {culprit['method']}
  - False alibi (to demolish): {culprit['alibi']}
Full backstory: {backstory}

Innocent suspects and why they are cleared:
{suspect_summary}

All clues (use ALL of them in your explanation):
{clue_summary}

=== END OF INVESTIGATION STORY ===
…{story_tail}

=== YOUR TASK ===
Continue directly from where the investigation ends. The detective now assembles \
ALL suspects in one room. Walk through EVERY clue above, explaining red herrings \
as deliberate misdirection. Demolish the culprit's false alibi using the \
evidence. Reveal the full truth of what happened. End with the culprit's \
arrest or confession. Complete the entire scene — do not leave it unfinished.
"""

    result = _safe_call_llm(
        prompt=prompt,
        model_name=NARRATOR_MODEL,
        system_instruction=REVELATION_SYSTEM,
        max_output_tokens=4096,
    )

    if result:
        print("✓")
        return result.strip()
    else:
        print("✗ (LLM returned empty — using backstory fallback)")
        return (
            f"The detective gathered the suspects and laid out the truth.\n\n"
            f"{backstory}\n\n"
            f"The culprit, {culprit['name']}, was arrested."
        )


# ─── Full story assembly ──────────────────────────────────────────────────────

def assemble_story(
    state: dict[str, Any],
    plot_points: list[str],
) -> str:
    """
    Orchestrate Phase 3: narrate + revelation → complete story string.
    """
    detective_name = _get_detective_name(state)
    victim_name    = state["victim"]["name"]
    setting        = state["setting"]["location"]
    date_          = state["setting"]["date"]

    header = (
        f"# {victim_name}: A Murder at {setting}\n"
        f"*{date_}*\n\n"
        f"---\n\n"
    )

    narrative  = narrate_plot_points(plot_points, state)
    revelation = write_revelation_scene(state, narrative)

    story = (
        header
        + narrative
        + "\n\n---\n\n## The Revelation\n\n"
        + revelation
        + "\n\n---\n\n*End of story. "
        + f"Detective: {detective_name} | Victim: {victim_name} | "
        + f"Setting: {setting}*\n"
    )

    return story


# ─── Safe LLM call (handles NoneType from Gemini) ────────────────────────────

def _safe_call_llm(
    prompt: str,
    model_name: str,
    system_instruction: str,
    max_output_tokens: int,
    retries: int = 3,
) -> str | None:
    """
    Wrapper around call_llm that handles the case where response.text is None.
    Gemini occasionally returns a response object with no text (safety filter
    or empty candidate). We retry up to `retries` times before giving up.
    """
    for attempt in range(1, retries + 1):
        try:
            result = call_llm(
                prompt=prompt,
                model_name=model_name,
                system_instruction=system_instruction,
                expect_json=False,
                temperature=PROSE_TEMPERATURE,
                max_output_tokens=max_output_tokens,
            )
            # Guard against None / empty string
            if result and result.strip():
                return result
            print(f"\n  [narrator] attempt {attempt}: empty response, retrying…", end=" ", flush=True)
        except RuntimeError as exc:
            print(f"\n  [narrator] attempt {attempt} failed: {exc}", end=" ", flush=True)
    return None


# ─── Helper ───────────────────────────────────────────────────────────────────

def _get_detective_name(state: dict[str, Any]) -> str:
    return state.get("detective", {}).get("name", "Detective Morgan Reyes")
