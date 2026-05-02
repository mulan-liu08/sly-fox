"""
phase1_generator.py — Lightweight Phase 1 crime-state generation for Phase 2.

This lets the interactive game start from a freshly generated crime state instead
of requiring a pre-existing crime_state_*.json file. It is based on the Phase 1
Sly Fox schema and prompt, but only generates the structured crime state needed
by the Phase 2 world builder.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

from config import OUTPUT_DIR, CRIME_GEN_MODEL, CRIME_GEN_TEMP, MIN_SUSPECTS, MIN_CLUES, MAX_CRIME_GEN_ATTEMPTS
from llm_client import call_llm


CRIME_GEN_SYSTEM = (
    "You are a master crime fiction writer and game designer specializing in "
    "intricate murder mysteries. Design the hidden ground truth of a mystery "
    "as structured data. Every fact you invent becomes binding for gameplay. "
    "Return only valid JSON when asked."
)


def generate_crime_state(seed_theme: str = "", save: bool = True) -> tuple[dict[str, Any], str | None]:
    """Generate and optionally save a Phase 1-compatible crime state."""
    prompt = _build_crime_prompt(seed_theme)
    last_error: Exception | None = None

    print("Phase 1 — Generating crime world state…")
    for attempt in range(1, MAX_CRIME_GEN_ATTEMPTS + 1):
        print(f"  Attempt {attempt}/{MAX_CRIME_GEN_ATTEMPTS}…", end=" ", flush=True)
        try:
            state = call_llm(
                prompt=prompt,
                model_name=CRIME_GEN_MODEL,
                system_instruction=CRIME_GEN_SYSTEM,
                expect_json=True,
                temperature=CRIME_GEN_TEMP,
                max_output_tokens=8192,
            )
            _validate_crime_state(state)
            path = _save_crime_state(state) if save else None
            print("✓")
            if path:
                print(f"  Crime state saved → {path}")
            return state, path
        except Exception as exc:
            last_error = exc
            print(f"failed ({exc})")
            time.sleep(1.0)

    raise RuntimeError("Could not generate a valid crime state") from last_error


def _save_crime_state(state: dict[str, Any]) -> str:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(OUTPUT_DIR, f"generated_crime_state_{run_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    return path


def _build_crime_prompt(seed_theme: str = "") -> str:
    theme_hint = f"Theme hint: {seed_theme}. " if seed_theme else ""
    return f"""\
{theme_hint}Design a complete hidden crime world state for a playable murder mystery text adventure.
Return ONLY a valid JSON object matching the schema below. No prose outside JSON.

Requirements:
- Exactly 1 culprit who has ALL THREE: means, motive, and opportunity.
- At least {MIN_SUSPECTS} innocent suspects; each must be missing at least one of means, motive, or opportunity.
- At least {MIN_CLUES} clues total.
- Include 1–2 red herrings for every 5 clues; red herrings must have plausible hindsight explanations.
- At least 2 clues should have prerequisite_clue_id values, creating a clue chain.
- The culprit's alibi must be false but should sound plausible if interviewed.
- Innocent suspects' alibis must be true and verifiable.
- Give clues concrete physical locations that can become rooms or objects in a text game.
- The hidden_backstory must be a single prose paragraph describing the full truth.

JSON Schema:
{{
  "setting": {{"location": "string", "date": "string", "time_of_crime": "string"}},
  "victim": {{"name": "string", "occupation": "string", "background": "string"}},
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
  "timeline": [{{"time": "string", "event": "string", "known_to_detective": false}}],
  "hidden_backstory": "string"
}}
"""


def _validate_crime_state(state: dict[str, Any]) -> None:
    required = ["setting", "victim", "culprit", "suspects", "clues", "timeline", "hidden_backstory"]
    for key in required:
        if key not in state:
            raise ValueError(f"missing {key}")
    if not isinstance(state.get("suspects"), list) or len(state["suspects"]) < MIN_SUSPECTS:
        raise ValueError(f"need at least {MIN_SUSPECTS} suspects")
    if not isinstance(state.get("clues"), list) or len(state["clues"]) < MIN_CLUES:
        raise ValueError(f"need at least {MIN_CLUES} clues")
    culprit = state.get("culprit", {})
    for key in ("name", "means", "motive", "opportunity", "method", "alibi"):
        if not culprit.get(key):
            raise ValueError(f"culprit missing {key}")
    ids: set[str] = set()
    for i, clue in enumerate(state["clues"], 1):
        clue.setdefault("id", f"clue_{i:02d}")
        ids.add(clue["id"])
        for key in ("description", "location", "points_to"):
            if key not in clue:
                raise ValueError(f"clue {clue.get('id')} missing {key}")
        clue.setdefault("is_red_herring", False)
        clue.setdefault("red_herring_explanation", None)
        clue.setdefault("prerequisite_clue_id", None)
    for clue in state["clues"]:
        prereq = clue.get("prerequisite_clue_id")
        if prereq and prereq not in ids:
            clue["prerequisite_clue_id"] = None
