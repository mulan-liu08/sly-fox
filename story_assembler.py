"""
story_assembler.py — Phase 3: Assemble the final story.

Two sub-components:
  1. FluentNarrator   — expands raw plot points into polished prose WITH dialogue
  2. RevelationWriter — generates the detective's final explanation scene

Key design decisions:
  - Single LLM call for narration (no batches) → no restarts or duplication
  - max_output_tokens=8192 for narration, 4096 for revelation → no truncation
  - NoneType guard with retries → handles empty Gemini responses
  - Detective name and setting locked in prompt → no LLM drift
  - Explicit dialogue rules → interrogations written as scenes, not summaries
  - Clue IDs stripped from revelation prompt → no [clue_01] leaking into prose
"""

from __future__ import annotations
from typing import Any

from llm_client import call_llm
from config import NARRATOR_MODEL, PROSE_TEMPERATURE


# ─── System instructions ──────────────────────────────────────────────────────

NARRATOR_SYSTEM = (
    "You are a literary crime fiction author in the tradition of Agatha Christie "
    "and Tana French. Your prose is atmospheric, precise, and psychologically acute. "
    "You expand a numbered list of raw plot-point summaries into one continuous, "
    "fully realized narrative — third-person limited from the detective's point of view. "
    "The output is a SINGLE UNBROKEN story from first plot point to last. "
    "Do NOT restart the story, do NOT re-introduce the detective more than once, "
    "do NOT repeat scene-setting. Maintain suspense throughout. "
    "NEVER reveal the killer's identity before the final revelation scene.\n\n"
    "CRITICAL — DIALOGUE REQUIREMENT:\n"
    "Every interrogation, interview, and confrontation scene MUST be written as a "
    "proper dialogue scene with actual spoken lines in quotation marks. "
    "Do NOT summarize what characters said — write their exact words. "
    "At least 40% of the text should be spoken dialogue. "
    "Use physical action beats between dialogue lines to show emotion and body language "
    "(e.g. 'He shifted in his seat', 'Her eyes darted to the floor'). "
    "Write at least 3-5 exchanges of back-and-forth dialogue per interrogation scene.\n\n"
    "EXAMPLE — do NOT write this:\n"
    "  'Reyes questioned Vance about his whereabouts. He denied being on that floor.'\n"
    "EXAMPLE — DO write this:\n"
    "  'Where were you at ten-fifteen?' Reyes placed the key card log on the table.\n"
    "  Vance's eyes flicked to the paper, then back to her face. 'My office. Working late.'\n"
    "  'Your card was scanned on Level 7 at ten-twelve.'\n"
    "  A pause. Something moved behind his eyes. 'That's — that must be a system error.'\n"
    "  'We've had the system checked.' She held his gaze. 'Try again.'"
)

REVELATION_SYSTEM = (
    "You are writing the climactic revelation scene of a crime mystery novel. "
    "The detective gathers all suspects and walks through the hidden truth of what "
    "happened, step by step, revealing how the crime was committed and who did it. "
    "This scene must be written as DRAMATIC DIALOGUE — the detective speaks aloud, "
    "suspects react with spoken lines, interruptions, denials, and eventual breakdown. "
    "Do NOT write this as a monologue or a report — it is a live, tense scene. "
    "This scene should be dramatically satisfying, tying every clue and red herring "
    "back to the truth. Write in vivid, literary third-person prose with dialogue. "
    "Write at least 600 words. Do NOT stop mid-sentence. Complete the full scene "
    "including the culprit's arrest or confession before you stop."
)


# ─── Fluent Narrator ─────────────────────────────────────────────────────────

def narrate_plot_points(
    plot_points: list[str],
    state: dict[str, Any],
) -> str:
    """
    Expand ALL raw plot points into one continuous narrative in a single LLM call.
    Dialogue is explicitly required in every interrogation/confrontation scene.
    """
    print("\n✍️   Phase 3a — Fluent narration (single call)…", end=" ", flush=True)

    detective_name = _get_detective_name(state)
    victim_name    = state["victim"]["name"]
    setting        = state["setting"]["location"]
    date_          = state["setting"]["date"]

    numbered = "\n".join(f"{i+1}. {pp}" for i, pp in enumerate(plot_points))

    prompt = (
        "You are writing a complete crime mystery investigation story.\n\n"
        "FIXED DETAILS — use these exactly, do not change or invent alternatives:\n"
        f"  Setting: {setting}\n"
        f"  Date: {date_}\n"
        f"  Victim: {victim_name}\n"
        f"  Detective name: {detective_name}  <-- use THIS name throughout, never rename them\n\n"
        f"Below are {len(plot_points)} plot points in order. "
        "Expand them into ONE continuous, unbroken third-person narrative. "
        "Each plot point should become 1-3 paragraphs. "
        "Do NOT number the paragraphs. Do NOT restart the story partway through. "
        f"The detective's name is {detective_name} — never call them anything else. "
        "Introduce the detective only ONCE at the very beginning. "
        "Transition smoothly between every plot point. "
        "Do NOT reveal who the killer is — that comes in a separate scene afterward. "
        "Write until you have covered every single plot point.\n\n"
        "DIALOGUE RULES — these are mandatory:\n"
        "1. Every plot point that involves questioning, interviewing, or confronting "
        "a suspect MUST be written as a scene with actual spoken dialogue in quotation marks.\n"
        "2. Do NOT summarize conversations. Write the actual words spoken.\n"
        "   WRONG: 'The detective questioned Vance, who gave a vague answer.'\n"
        "   RIGHT: 'Where were you at ten-fifteen?' Reyes set the photograph on the table.\n"
        "           Vance's jaw tightened. 'I already told your colleague — I was in my office.'\n"
        "           'Your key card says otherwise.' She held his gaze without blinking.\n"
        "           He looked away first. 'There must be some mistake.'\n"
        "3. Write at least 4-6 back-and-forth exchanges per interrogation.\n"
        "4. Between dialogue lines, include action beats showing the character's "
        "emotional state through body language (fidgeting, eye contact, posture, etc.).\n"
        "5. Suspects should push back, deflect, and lie — not instantly confess.\n\n"
        "PLOT POINTS:\n"
        f"{numbered}"
    )

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
        print("✗ (LLM returned empty — using raw plot points as fallback)")
        return "\n\n".join(plot_points)


# ─── Revelation Scene Writer ──────────────────────────────────────────────────

def write_revelation_scene(
    state: dict[str, Any],
    story_so_far: str,
) -> str:
    """
    Generate the detective's final revelation scene as a live dramatic dialogue scene.
    """
    print("    Writing revelation scene…", end=" ", flush=True)

    culprit       = state["culprit"]
    victim        = state["victim"]
    clues         = state["clues"]
    suspects      = state["suspects"]
    backstory     = state.get("hidden_backstory", "")
    detective_name = _get_detective_name(state)

    # Clue descriptions — NO IDs, just natural language
    clue_summary = "\n".join(
        f"  - {c['description']}"
        + (f" (RED HERRING — real explanation: {c['red_herring_explanation']})"
           if c.get("is_red_herring") else "")
        for c in clues
    )

    suspect_summary = "\n".join(
        f"  - {s['name']} ({s['occupation']}): "
        f"why cleared = lacks {s['missing_element']}; alibi: {s['alibi']}"
        for s in suspects
    )

    story_tail = story_so_far[-2000:] if len(story_so_far) > 2000 else story_so_far

    prompt = (
        "You are writing the COMPLETE final revelation scene of a murder mystery.\n"
        "Write at least 600 words. Do not stop until the scene ends with the "
        "culprit's arrest or confession.\n\n"
        f"Detective name: {detective_name}  <-- use this name exactly\n\n"
        "=== HIDDEN GROUND TRUTH (now to be revealed) ===\n"
        f"Victim: {victim['name']} — {victim['background']}\n"
        f"Culprit: {culprit['name']}\n"
        f"  - Means: {culprit['means']}\n"
        f"  - Motive: {culprit['motive']}\n"
        f"  - Opportunity: {culprit['opportunity']}\n"
        f"  - Method: {culprit['method']}\n"
        f"  - False alibi (to demolish): {culprit['alibi']}\n"
        f"Full backstory: {backstory}\n\n"
        "Innocent suspects and why they are cleared:\n"
        f"{suspect_summary}\n\n"
        "All clues — reference ALL of them naturally in dialogue "
        "(do NOT use IDs like [clue_01] — describe them as objects/evidence):\n"
        f"{clue_summary}\n\n"
        "=== END OF INVESTIGATION STORY ===\n"
        f"...{story_tail}\n\n"
        "=== YOUR TASK ===\n"
        "Continue directly from where the investigation ends. "
        f"{detective_name} assembles ALL suspects in one room. "
        "Write this as a DRAMATIC DIALOGUE SCENE — the detective speaks aloud, "
        "suspects react with spoken lines, interruptions, denials, protests. "
        "Clear each innocent suspect one by one with spoken reasoning. "
        "Build to the culprit reveal. Demolish the culprit's false alibi with evidence. "
        "The culprit should react — deny, break down, or confess in spoken dialogue. "
        "End with their arrest. Do NOT write this as a monologue or report — "
        "it must be a live scene with back-and-forth spoken exchanges."
    )

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

    return (
        header
        + narrative
        + "\n\n---\n\n## The Revelation\n\n"
        + revelation
        + "\n\n---\n\n"
        + f"*End of story. Detective: {detective_name} | "
        + f"Victim: {victim_name} | Setting: {setting}*\n"
    )


# ─── Safe LLM call (handles NoneType from Gemini) ────────────────────────────

def _safe_call_llm(
    prompt: str,
    model_name: str,
    system_instruction: str,
    max_output_tokens: int,
    retries: int = 3,
) -> str | None:
    """
    Wrapper around call_llm that handles None / empty responses gracefully.
    Gemini occasionally returns a response object with no text (transient issue
    or soft safety filter). Retries up to `retries` times before giving up.
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
            if result and result.strip():
                return result
            print(f"\n  [narrator] attempt {attempt}: empty response, retrying…",
                  end=" ", flush=True)
        except RuntimeError as exc:
            print(f"\n  [narrator] attempt {attempt} failed: {exc}",
                  end=" ", flush=True)
    return None


# ─── Helper ───────────────────────────────────────────────────────────────────

def _get_detective_name(state: dict[str, Any]) -> str:
    return state.get("detective", {}).get("name", "Detective Morgan Reyes")
