"""
Phase 1 — Structure:   No unconnected clues, red herrings are plausible.
Phase 2 — Complexity:  Counts meet the rubric thresholds.
Phase 3 — Consistency: Alibis, culprit MMO, timeline, no contradictions.
"""

from __future__ import annotations
from typing import Any

from config import (
    MIN_SUSPECTS,
    MIN_CLUES,
    RED_HERRING_RATIO,
    MIN_PLOT_POINTS,
)


def validate_crime_world_state(state: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    warnings += _phase1_structure(state)
    warnings += _phase2_complexity(state)
    warnings += _phase3_consistency(state)
    return warnings


def _phase1_structure(state: dict) -> list[str]:
    warnings: list[str] = []
    clues = state.get("clues", [])
    clue_ids = {c["id"] for c in clues}

    for clue in clues:
        prereq = clue.get("prerequisite_clue_id")
        if prereq and prereq not in clue_ids:
            raise ValueError(
                f"Clue {clue['id']!r} references non-existent prerequisite {prereq!r}"
            )
        if clue.get("is_red_herring") and not clue.get("red_herring_explanation"):
            raise ValueError(
                f"Red herring clue {clue['id']!r} has no red_herring_explanation"
            )
        known_names = _all_character_names(state)
        if clue.get("points_to") not in known_names and clue.get("points_to") != "culprit":
            warnings.append(
                f"Clue {clue['id']!r} points_to unknown name {clue['points_to']!r} "
                f"(may be intentional)"
            )

    return warnings


def _phase2_complexity(state: dict) -> list[str]:
    warnings: list[str] = []
    clues = state.get("clues", [])
    suspects = state.get("suspects", [])

    if len(clues) < MIN_CLUES:
        raise ValueError(f"Need ≥{MIN_CLUES} clues; found {len(clues)}")

    rh_count = sum(1 for c in clues if c.get("is_red_herring"))
    min_rh = (len(clues) // 5) * RED_HERRING_RATIO[0]
    max_rh = (len(clues) // 5) * RED_HERRING_RATIO[1]
    if rh_count < min_rh:
        raise ValueError(
            f"Too few red herrings: {rh_count} (need ≥{min_rh} for {len(clues)} clues)"
        )
    if rh_count > max_rh and max_rh > 0:
        warnings.append(
            f"More red herrings than expected: {rh_count} vs max ~{max_rh}"
        )

    chained = sum(1 for c in clues if c.get("prerequisite_clue_id"))
    if chained < 2:
        raise ValueError(
            f"Need ≥2 chained clues; found {chained}"
        )

    if len(suspects) < MIN_SUSPECTS:
        raise ValueError(f"Need ≥{MIN_SUSPECTS} suspects; found {len(suspects)}")

    for s in suspects:
        missing = [k for k in ("means", "motive", "opportunity") if not s.get(k)]
        if len(missing) == 0:
            raise ValueError(
                f"Innocent suspect {s.get('name')!r} has all three MMO elements — "
                "they must be missing at least one."
            )
        if len(missing) == 3:
            warnings.append(
                f"Suspect {s.get('name')!r} is missing ALL three MMO elements — "
                "barely a suspect."
            )

    return warnings


def _phase3_consistency(state: dict) -> list[str]:
    warnings: list[str] = []
    culprit = state.get("culprit", {})

    for element in ("means", "motive", "opportunity"):
        if not culprit.get(element):
            raise ValueError(
                f"Culprit {culprit.get('name')!r} is missing {element!r}"
            )

    if not culprit.get("method"):
        raise ValueError("Culprit has no method of murder specified")

    if not culprit.get("alibi"):
        raise ValueError("Culprit has no (false) alibi — they need one to be a suspect")

    timeline = state.get("timeline", [])
    if len(timeline) < 3:
        warnings.append("Timeline has fewer than 3 events — consider adding more detail")

    clues = state.get("clues", [])
    ids = [c["id"] for c in clues]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate clue IDs detected")

    victim = state.get("victim", {})
    if not victim.get("name"):
        raise ValueError("Victim has no name")

    return warnings


def _all_character_names(state: dict) -> set[str]:
    names = set()
    if state.get("culprit", {}).get("name"):
        names.add(state["culprit"]["name"])
    for s in state.get("suspects", []):
        if s.get("name"):
            names.add(s["name"])
    return names


def summarise_crime_state(state: dict) -> str:
    culprit_name = state.get("culprit", {}).get("name", "?")
    victim_name  = state.get("victim", {}).get("name", "?")
    n_suspects   = len(state.get("suspects", []))
    n_clues      = len(state.get("clues", []))
    n_rh         = sum(1 for c in state.get("clues", []) if c.get("is_red_herring"))
    setting      = state.get("setting", {}).get("location", "?")
    return (
        f"Victim={victim_name!r}, Culprit={culprit_name!r}, "
        f"Suspects={n_suspects}, Clues={n_clues} ({n_rh} red herrings), "
        f"Setting={setting!r}"
    )
