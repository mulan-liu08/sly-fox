"""
story_assembler.py — Phase 3: Assemble the final story.

Two sub-components:
  1. FluentNarrator   — takes raw plot points and expands them into polished prose.
  2. RevelationWriter — generates the detective's final explanation scene.

The output is a complete, suspenseful crime mystery story as a single string.
"""

from __future__ import annotations
from typing import Any

from llm_client import call_llm
from config import NARRATOR_MODEL


# ─── System instructions ──────────────────────────────────────────────────────

NARRATOR_SYSTEM = """\
You are a literary crime fiction author in the tradition of Agatha Christie \
and Tana French. Your prose is atmospheric, precise, and psychologically acute. \
You expand raw plot-point summaries into fully realized narrative prose — \
third-person limited from the detective's point of view. Maintain suspense \
throughout. Never reveal the killer's identity before the final revelation scene.
"""

REVELATION_SYSTEM = """\
You are writing the climactic revelation scene of a crime mystery novel. \
The detective gathers all suspects and walks through the hidden truth of what \
happened, step by step, revealing how the crime was committed and who did it. \
This scene should be dramatically satisfying, tying every clue and red herring \
back to the truth. Write in vivid, literary third-person prose.
"""


# ─── Fluent Narrator ─────────────────────────────────────────────────────────

def narrate_plot_points(
    plot_points: list[str],
    state: dict[str, Any],
) -> str:
    """
    Expand the raw plot points into polished narrative prose.

    We process them in batches of 5 to stay within token limits, then
    concatenate the results.
    """
    print("\n✍️   Phase 3a — Fluent narration…")

    detective_name = _get_detective_name(state)
    victim_name    = state["victim"]["name"]
    setting        = state["setting"]["location"]
    date_          = state["setting"]["date"]

    sections: list[str] = []
    batch_size = 5

    for i in range(0, len(plot_points), batch_size):
        batch = plot_points[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(plot_points) + batch_size - 1) // batch_size
        print(f"    Narrating batch {batch_num}/{total_batches}…", end=" ", flush=True)

        numbered = "\n".join(f"{j+1}. {pp}" for j, pp in enumerate(batch))
        prompt = f"""\
Setting: {setting}, {date_}
Victim: {victim_name}
Detective: {detective_name}

Raw plot points to expand into narrative prose:
{numbered}

Expand each plot point into 1–3 vivid paragraphs of third-person narrative prose. \
Maintain chronological order. Do NOT number the paragraphs. \
Maintain suspense — do not reveal the killer. \
Transition smoothly between plot points.
"""
        try:
            section = call_llm(
                prompt=prompt,
                model_name=NARRATOR_MODEL,
                system_instruction=NARRATOR_SYSTEM,
                expect_json=False,
                temperature=0.88,
                max_output_tokens=2048,
            )
            sections.append(section.strip())
            print("✓")
        except RuntimeError as exc:
            print(f"✗ ({exc}) — using raw plot points as fallback")
            sections.append("\n\n".join(batch))

    return "\n\n".join(sections)


# ─── Revelation Scene Writer ──────────────────────────────────────────────────

def write_revelation_scene(
    state: dict[str, Any],
    story_so_far: str,
) -> str:
    """
    Generate the detective's final revelation scene.

    The LLM receives the FULL crime world state (ground truth) and the
    narrated story so far, and writes a climactic scene where the detective
    reveals the truth.
    """
    print("    Writing revelation scene…", end=" ", flush=True)

    culprit   = state["culprit"]
    victim    = state["victim"]
    clues     = state["clues"]
    backstory = state.get("hidden_backstory", "")

    clue_summary = "\n".join(
        f"  - {c['description']}"
        + (" (RED HERRING)" if c.get("is_red_herring") else "")
        for c in clues
    )

    prompt = f"""\
You are writing the final revelation scene of a murder mystery.

=== HIDDEN GROUND TRUTH (now to be revealed) ===
Victim: {victim['name']} — {victim['background']}
Culprit: {culprit['name']}
  - Means: {culprit['means']}
  - Motive: {culprit['motive']}
  - Opportunity: {culprit['opportunity']}
  - Method: {culprit['method']}
  - False alibi: {culprit['alibi']}
Backstory: {backstory}

Clues in the case:
{clue_summary}

=== THE STORY SO FAR (last 500 chars) ===
…{story_so_far[-500:]}

=== YOUR TASK ===
Write the dramatic revelation scene (400–700 words). The detective assembles \
all the suspects, walks through every clue (explaining red herrings as \
deliberate misdirection), demolishes the culprit's alibi, and reveals the full \
truth of what happened. End with the culprit's arrest or confession.
"""

    try:
        scene = call_llm(
            prompt=prompt,
            model_name=NARRATOR_MODEL,
            system_instruction=REVELATION_SYSTEM,
            expect_json=False,
            temperature=0.85,
            max_output_tokens=2048,
        )
        print("✓")
        return scene.strip()
    except RuntimeError as exc:
        print(f"✗ ({exc})")
        return (
            f"[REVELATION SCENE GENERATION FAILED — {exc}]\n\n"
            f"Hidden truth: {backstory}"
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

    # Title block
    header = (
        f"# The {setting} Murder\n"
        f"*A crime mystery — {date_}*\n\n"
        f"---\n\n"
    )

    # Narrate the investigation
    narrative = narrate_plot_points(plot_points, state)

    # Revelation scene
    revelation = write_revelation_scene(state, narrative)

    # Stitch together
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


# ─── Helper: infer or invent detective name ───────────────────────────────────

def _get_detective_name(state: dict[str, Any]) -> str:
    """Check if state has a detective field, else return a default."""
    return state.get("detective", {}).get("name", "Detective Morgan Reyes")
