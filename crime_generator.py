"""
Output schema (CrimeWorldState):
{
  "setting": { "location": str, "date": str, "time_of_crime": str },
  "victim": { "name": str, "occupation": str, "background": str },
  "culprit": {
      "name": str,
      "means": str,
      "motive": str,
      "opportunity": str,
      "method": str,        # how the murder was committed
      "alibi": str          # the alibi the culprit gives (FALSE)
  },
  "suspects": [             # 3+ innocent suspects (culprit excluded)
      {
          "name": str,
          "occupation": str,
          "relationship_to_victim": str,
          "means": str | null,      # null = lacks this element
          "motive": str | null,
          "opportunity": str | null,
          "alibi": str,             # true alibi (verifiable)
          "personality": str,       # response pattern for consistency checker
          "missing_element": str    # "means" | "motive" | "opportunity"
      }
  ],
  "clues": [                # at least 5
      {
          "id": str,                    # e.g. "clue_01"
          "description": str,
          "location": str,
          "points_to": str,             # suspect name OR "culprit"
          "is_red_herring": bool,
          "red_herring_explanation": str | null,   # hindsight explanation if red herring
          "prerequisite_clue_id": str | null        # must discover this clue first
      }
  ],
  "timeline": [             # ordered list of events on the night of the crime
      { "time": str, "event": str, "known_to_detective": bool }
  ],
  "hidden_backstory": str   # prose paragraph: full truth of what happened
}
"""

from __future__ import annotations
import json
from typing import Any
import time

from llm_client import call_llm
from config import CRIME_GEN_MODEL, MIN_SUSPECTS, MIN_CLUES


CRIME_GEN_SYSTEM = """\
You are a master crime fiction writer and game designer specializing in \
intricate murder mysteries. Your job is to design the hidden GROUND TRUTH \
of a murder mystery — the full truth that the detective must eventually \
uncover. Be creative, specific, and internally consistent. Every detail you \
invent becomes a binding constraint for the rest of the story.
"""


def _build_crime_prompt(seed_theme: str = "") -> str:
    theme_hint = f"Theme hint: {seed_theme}. " if seed_theme else ""
    return f"""\
{theme_hint}Design a complete hidden crime world state for a murder mystery. \
Return ONLY a valid JSON object matching the schema below. No prose outside the JSON.

Requirements:
- Exactly 1 culprit who has ALL THREE of: means, motive, opportunity.
- At least {MIN_SUSPECTS} innocent suspects, each MISSING at least one of means/motive/opportunity \
  (set the missing field to null and specify which element is missing in "missing_element").
- At least {MIN_CLUES} clues total. 1–2 of every 5 clues must be red herrings \
  (is_red_herring: true). Red herrings must have a plausible hindsight explanation.
- At least 2 clues must have a prerequisite_clue_id (chain clues).
- The culprit's alibi must be FALSE and verifiably breakable.
- All innocent suspects' alibis must be TRUE.
- The hidden_backstory must be a single prose paragraph describing the full truth.
- Be original and avoid clichés (no butlers, no identical twins).

JSON Schema:
{{
  "setting": {{ "location": "string", "date": "string", "time_of_crime": "string" }},
  "victim": {{ "name": "string", "occupation": "string", "background": "string" }},
  "culprit": {{
    "name": "string",
    "means": "string",
    "motive": "string",
    "opportunity": "string",
    "method": "string",
    "alibi": "string"
  }},
  "suspects": [
    {{
      "name": "string",
      "occupation": "string",
      "relationship_to_victim": "string",
      "means": "string or null",
      "motive": "string or null",
      "opportunity": "string or null",
      "alibi": "string",
      "personality": "string",
      "missing_element": "means|motive|opportunity"
    }}
  ],
  "clues": [
    {{
      "id": "clue_01",
      "description": "string",
      "location": "string",
      "points_to": "string (suspect name or 'culprit')",
      "is_red_herring": false,
      "red_herring_explanation": null,
      "prerequisite_clue_id": null
    }}
  ],
  "timeline": [
    {{ "time": "string", "event": "string", "known_to_detective": false }}
  ],
  "hidden_backstory": "string"
}}
"""


def generate_crime_world_state(seed_theme: str = "") -> dict[str, Any]:
    print("Phase 1 — Generating crime world state…")

    from config import MAX_REGEN_ATTEMPTS
    prompt = _build_crime_prompt(seed_theme)

    for attempt in range(1, MAX_REGEN_ATTEMPTS + 1):
        time.sleep(2)
        print(f"Attempt {attempt}/{MAX_REGEN_ATTEMPTS}…", end=" ", flush=True)
        try:
            state: dict = call_llm(
                prompt=prompt,
                model_name=CRIME_GEN_MODEL,
                system_instruction=CRIME_GEN_SYSTEM,
                expect_json=True,
                temperature=0.2,
                max_output_tokens=8192,
            )
            _validate_raw_state(state)
            print("Good")
            return state
        except (ValueError, KeyError, RuntimeError) as exc:
            print(f"Bad ({exc})")
            if attempt == MAX_REGEN_ATTEMPTS:
                raise RuntimeError(
                    "Crime world state generation failed after all attempts."
                ) from exc

    raise RuntimeError("Unreachable")


def _validate_raw_state(state: dict) -> None:
    required_top = ["setting", "victim", "culprit", "suspects", "clues",
                    "timeline", "hidden_backstory"]
    for key in required_top:
        if key not in state:
            raise ValueError(f"Missing top-level key: {key!r}")

    if len(state["suspects"]) < MIN_SUSPECTS:
        raise ValueError(
            f"Need ≥{MIN_SUSPECTS} suspects, got {len(state['suspects'])}"
        )
    if len(state["clues"]) < MIN_CLUES:
        raise ValueError(
            f"Need ≥{MIN_CLUES} clues, got {len(state['clues'])}"
        )
    for s in state["suspects"]:
        if s.get("missing_element") not in ("means", "motive", "opportunity"):
            raise ValueError(
                f"Suspect {s.get('name')!r} has invalid missing_element"
            )
