"""
story_assembler.py — Phase 3: Assemble the final story.

Two sub-components:
  1. FluentNarrator   — expands raw plot points into polished prose WITH dialogue
  2. RevelationWriter — generates the detective's final explanation scene

Key design decisions:
  - Crime world state injected into BOTH narration and revelation prompts so
    the LLM cannot invent new evidence, clue names, or murder methods
  - Suspect roster with alibis passed explicitly so the revelation assembles
    only the physically present suspects (not those confirmed out-of-town)
  - Single LLM call for narration → no restarts or duplication
  - max_output_tokens=8192 narration, 4096 revelation → no truncation
  - NoneType guard with retries → handles empty Gemini responses
  - Detective name and setting locked → no LLM drift
  - Explicit dialogue rules → interrogations as scenes, not summaries
  - Clue IDs stripped → no [clue_01] leaking into prose
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
    "CONSTRAINT — FACTS ARE FIXED:\n"
    "A crime world state will be provided. The clues, suspects, murder method, "
    "and culprit alibi listed there are the ONLY facts you may use. "
    "Do NOT invent new evidence, new clue names, new project names, new locations, "
    "or new murder weapons that are not in the crime world state. "
    "Do NOT invent names for sub-projects, access systems, or technology that "
    "are not explicitly listed in the crime world state. "
    "If a plot point mentions a clue, describe it using the exact wording from "
    "the crime world state. You may add atmosphere, emotion, and dialogue — "
    "but every FACT must come from the crime world state, never from your imagination.\n\n"
    "CRITICAL — DIALOGUE REQUIREMENT:\n"
    "Every interrogation, interview, and confrontation scene MUST be written as a "
    "proper dialogue scene with actual spoken lines in quotation marks. "
    "Do NOT summarize what characters said — write their exact words. "
    "At least 40% of the text should be spoken dialogue. "
    "Use physical action beats between dialogue lines to show emotion and body language. "
    "Write at least 4-6 exchanges of back-and-forth dialogue per interrogation scene. "
    "Suspects should push back, deflect, and lie — not instantly confess.\n\n"
    "EXAMPLE — do NOT write this:\n"
    "  'Reyes questioned Vance about his whereabouts. He denied being on that floor.'\n"
    "EXAMPLE — DO write this:\n"
    "  'Where were you at ten-fifteen?' Reyes placed the key card log on the table.\n"
    "  Vance's eyes flicked to the paper, then back to her face. 'My office. Working late.'\n"
    "  'Your card was scanned on Level 7 at ten-twelve.'\n"
    "  A pause. Something moved behind his eyes. 'That must be a system error.'\n"
    "  'We've had the system checked.' She held his gaze. 'Try again.'"
)

REVELATION_SYSTEM = (
    "You are writing the climactic revelation scene of a crime mystery novel. "
    "The detective gathers the physically present suspects and walks through the "
    "hidden truth of what happened, step by step. "
    "This scene must be DRAMATIC DIALOGUE — the detective speaks aloud, "
    "suspects react with spoken lines, interruptions, denials, and eventual breakdown. "
    "Do NOT write this as a monologue or a report — it is a live, tense scene. "
    "Only include suspects who could physically be present — do NOT include suspects "
    "whose alibis place them in another city or who are confirmed to be elsewhere. "
    "Write in vivid, literary third-person prose with dialogue. "
    "Write at least 600 words. Do NOT stop mid-sentence. Complete the full scene "
    "including the culprit's arrest or confession before you stop."
)


# ─── helpers to build crime world context blocks ─────────────────────────────

def _build_clue_block(clues: list[dict]) -> str:
    """Plain-language clue list with no IDs — for the narration prompt."""
    lines = []
    for c in clues:
        line = f"  - {c['description']} (found at: {c['location']})"
        if c.get("is_red_herring"):
            line += f" [RED HERRING — real explanation: {c['red_herring_explanation']}]"
        lines.append(line)
    return "\n".join(lines)


def _build_suspect_block(suspects: list[dict]) -> str:
    """Suspect roster with alibi and physical-presence flag — for both prompts."""
    lines = []
    for s in suspects:
        alibi = s.get("alibi", "unknown")
        # Flag suspects whose alibis place them physically elsewhere
        out_of_town = any(
            phrase in alibi.lower()
            for phrase in ["conference", "stanford", "university", "flight",
                           "hotel", "livestream", "keynote", "home", "sick",
                           "flu", "hospital", "miles away", "across the country"]
        )
        presence = "NOT physically present at facility" if out_of_town else "present at facility"
        lines.append(
            f"  - {s['name']} ({s['occupation']}): "
            f"missing {s['missing_element']}, {presence}\n"
            f"    alibi: {alibi}"
        )
    return "\n".join(lines)


# ─── Fluent Narrator ─────────────────────────────────────────────────────────

def narrate_plot_points(
    plot_points: list[str],
    state: dict[str, Any],
) -> str:
    """
    Expand ALL raw plot points into one continuous narrative in a single LLM call.
    The full crime world state is injected so the LLM cannot invent new facts.
    """
    print("\n✍️   Phase 3a — Fluent narration (single call)…", end=" ", flush=True)

    detective_name = _get_detective_name(state)
    victim_name    = state["victim"]["name"]
    setting        = state["setting"]["location"]
    date_          = state["setting"]["date"]
    culprit_name   = state["culprit"]["name"]
    method         = state["culprit"]["method"]

    numbered     = "\n".join(f"{i+1}. {pp}" for i, pp in enumerate(plot_points))
    clue_block   = _build_clue_block(state.get("clues", []))
    suspect_block = _build_suspect_block(state.get("suspects", []))

    prompt = (
        "You are writing a complete crime mystery investigation story.\n\n"
        "=== FIXED FACTS — use ONLY these, invent nothing new ===\n"
        f"  Setting: {setting}\n"
        f"  Date: {date_}\n"
        f"  Victim: {victim_name}\n"
        f"  Detective name: {detective_name}  <-- ONLY name for the detective, never change it\n"
        f"  Murder method: {method}\n\n"
        "Suspects (use ONLY these people, do not invent others):\n"
        f"{suspect_block}\n\n"
        "Clues (use ONLY these clues, do not invent new evidence or project names):\n"
        f"{clue_block}\n\n"
        "=== YOUR TASK ===\n"
        f"Below are {len(plot_points)} plot points in order. "
        "Expand them into ONE continuous, unbroken third-person narrative. "
        "Each plot point should become 1-3 paragraphs. "
        "Do NOT number paragraphs. Do NOT restart the story partway through. "
        f"The detective's name is {detective_name} — never call them anything else. "
        "Introduce the detective only ONCE at the very beginning. "
        "Transition smoothly between plot points. "
        "Do NOT reveal the killer's identity — that comes in a separate scene. "
        "Do NOT invent new sub-project names, access systems, tokens, or technology "
        "that are not listed above. Stick strictly to the facts provided.\n\n"
        "DIALOGUE RULES — mandatory:\n"
        "1. Every interrogation or confrontation MUST contain actual quoted dialogue.\n"
        "2. Do NOT summarize conversations — write the words spoken.\n"
        "   WRONG: 'Reyes questioned Vance, who denied involvement.'\n"
        "   RIGHT: 'Where were you at one AM?' Reyes set the log on the table.\n"
        "           Vance's jaw tightened. 'In the server room. All night.'\n"
        "           'The cameras confirm that.' She paused. 'What about before eleven?'\n"
        "3. Write 4-6 exchanges per interrogation with body language beats between lines.\n"
        "4. Suspects push back and deflect — they do not confess immediately.\n\n"
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
    Generate the detective's final revelation scene.
    Only physically present suspects are seated at the table.
    Clue IDs are stripped so they don't leak into prose.
    """
    print("    Writing revelation scene…", end=" ", flush=True)

    culprit        = state["culprit"]
    victim         = state["victim"]
    clues          = state["clues"]
    suspects       = state["suspects"]
    backstory      = state.get("hidden_backstory", "")
    detective_name = _get_detective_name(state)

    # Split suspects into present vs. absent based on alibi content
    present_suspects = []
    absent_suspects  = []
    out_of_town_phrases = [
        "conference", "stanford", "university", "flight", "hotel",
        "livestream", "keynote", "home", "sick", "flu", "hospital",
        "miles away", "across the country"
    ]
    for s in suspects:
        alibi = s.get("alibi", "").lower()
        if any(p in alibi for p in out_of_town_phrases):
            absent_suspects.append(s)
        else:
            present_suspects.append(s)

    present_names = ", ".join(s["name"] for s in present_suspects)
    absent_lines  = "\n".join(
        f"  - {s['name']}: alibi confirmed — {s['alibi'][:120]}… (NOT in the room)"
        for s in absent_suspects
    )

    clue_summary = "\n".join(
        f"  - {c['description']}"
        + (f" (RED HERRING — real explanation: {c['red_herring_explanation']})"
           if c.get("is_red_herring") else "")
        for c in clues
    )

    suspect_summary = _build_suspect_block(suspects)
    story_tail = story_so_far[-2000:] if len(story_so_far) > 2000 else story_so_far

    prompt = (
        "You are writing the COMPLETE final revelation scene of a murder mystery.\n"
        "Write at least 600 words. Do not stop until the scene ends with arrest or confession.\n\n"
        f"Detective name: {detective_name}  <-- use this name exactly\n\n"
        "=== SUSPECTS PHYSICALLY IN THE ROOM ===\n"
        f"Only these suspects are seated at the table: {culprit['name']}"
        + (f", {present_names}" if present_names else "")
        + "\n\n"
        "=== SUSPECTS NOT IN THE ROOM (cleared by alibi, mentioned in passing only) ===\n"
        f"{absent_lines}\n\n"
        "=== HIDDEN GROUND TRUTH ===\n"
        f"Victim: {victim['name']} — {victim['background']}\n"
        f"Culprit: {culprit['name']}\n"
        f"  - Means: {culprit['means']}\n"
        f"  - Motive: {culprit['motive']}\n"
        f"  - Opportunity: {culprit['opportunity']}\n"
        f"  - Method: {culprit['method']}\n"
        f"  - False alibi to demolish: {culprit['alibi']}\n"
        f"Full backstory: {backstory}\n\n"
        "All clues — reference ALL naturally in dialogue (no bracket IDs in prose):\n"
        f"{clue_summary}\n\n"
        "=== END OF INVESTIGATION STORY ===\n"
        f"...{story_tail}\n\n"
        "=== YOUR TASK ===\n"
        f"{detective_name} assembles ONLY the physically present suspects listed above. "
        "Do NOT seat absent suspects at the table — they may be mentioned briefly as "
        "'cleared by confirmed alibi' without being physically present. "
        "Write this as a DRAMATIC DIALOGUE SCENE. The detective speaks, suspects react "
        "with spoken lines, interruptions, denials. Clear each present innocent suspect "
        "one by one. Build to the culprit reveal. Demolish the false alibi with evidence. "
        "The culprit denies, then breaks. End with arrest. "
        "Do NOT write this as a monologue — it must be live back-and-forth dialogue."
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
