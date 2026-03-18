"""
  Steps 1–3   : ESTABLISH   — scene, detective intro, first look at crime scene
  Steps 4–6   : ESCALATE    — initial suspects, early clues, first red herring
  Steps 7–10  : PIVOT       — obstacles, false leads, alibi checks, tension rises
  Steps 11–13 : CLIMAX      — major revelation, alibi broken, suspects narrow
  Steps 14–15 : RESOLVE     — confirmation, confrontation, case cracked

At each step the MetaController:
  1. Builds a context-rich prompt (previous plot points + crime facts available).
  2. Calls the LLM (PLOT_GEN_MODEL) to propose a new plot point.
  3. Passes the proposal to ConsistencyChecker.
  4. If valid → add to accumulator.
  5. If invalid → retry up to MAX_REGEN_ATTEMPTS with an adjusted prompt.
"""

from __future__ import annotations
from typing import Any

from llm_client import call_llm
from consistency_checker import ConsistencyChecker
from config import (
    PLOT_GEN_MODEL,
    TARGET_PLOT_POINTS,
    MIN_PLOT_POINTS,
    MAX_REGEN_ATTEMPTS,
    PROSE_TEMPERATURE,
)

def _arc_instruction(step: int, total: int) -> str:
    frac = step / total
    if frac <= 0.20:
        return (
            "ESTABLISH: Introduce the scene and the detective. Describe the crime "
            "scene vividly. The detective notices initial details but has no answers yet. "
            "Build atmosphere and reader affinity for the detective."
        )
    elif frac <= 0.40:
        return (
            "ESCALATE: Introduce a new suspect or a physical clue. The detective "
            "pursues a lead. Something makes the investigation slightly harder — "
            "a witness is evasive, or a clue is ambiguous. Tension rises."
        )
    elif frac <= 0.67:
        return (
            "PIVOT: The detective hits an obstacle. A false lead, an alibi that "
            "doesn't quite add up, or a red herring that sends them the wrong way. "
            "The goal feels harder to reach. At least one suspect should be "
            "beginning to look more suspicious."
        )
    elif frac <= 0.87:
        return (
            "CLIMAX: Major revelations. An alibi is broken, a key clue is uncovered, "
            "or the detective realises they've been misled. The real suspect is "
            "starting to become clear but is NOT yet named. Suspense peaks."
        )
    else:
        return (
            "RESOLVE: The detective has enough evidence. They confront or trap the "
            "culprit. The truth comes out — but the exact revelation is reserved "
            "for the final Revelation Scene written in Phase 3."
        )


def _build_context_summary(
    state: dict[str, Any],
    plot_points: list[str],
    revealed_clues: list[str],
) -> str:
    victim = state["victim"]["name"]
    setting = state["setting"]["location"]
    date    = state["setting"]["date"]

    suspects_block = "\n".join(
        f"  - {s['name']} ({s['occupation']}): "
        f"missing {s['missing_element']}"
        for s in state["suspects"]
    )

    clue_block = "\n".join(
        f"  - [{c['id']}] {c['description']}"
        + (" [RED HERRING — not yet player-known]" if c.get("is_red_herring") else "")
        for c in state["clues"]
        if c["id"] in revealed_clues
    )
    if not clue_block:
        clue_block = "  (none discovered yet)"

    prior_points = "\n".join(
        f"  Plot {i+1}: {pp}" for i, pp in enumerate(plot_points)
    )
    if not prior_points:
        prior_points = "  (this is the first plot point)"

    return f"""\
=== CRIME WORLD (HIDDEN GROUND TRUTH — do NOT contradict) ===
Victim: {victim}
Setting: {setting} on {date}
Time of crime: {state['setting']['time_of_crime']}

Suspects:
{suspects_block}

Clues discovered so far by the detective:
{clue_block}

=== STORY SO FAR ===
{prior_points}
"""


class MetaController:

    def __init__(self, state: dict[str, Any]):
        self.state    = state
        self.checker  = ConsistencyChecker(state, TARGET_PLOT_POINTS)
        self.plot_points: list[str] = []
        self.revealed_clues: list[str] = []

    def run(self) -> list[str]:
        print(f"\nPhase 2 — Iterative suspense loop (target: {TARGET_PLOT_POINTS} plot points)…")

        step = 1
        while len(self.plot_points) < TARGET_PLOT_POINTS:
            print(f"Step {step:02d}/{TARGET_PLOT_POINTS} → ", end="", flush=True)
            plot_point = self._generate_one_step(step)
            if plot_point:
                self.plot_points.append(plot_point)
                self._update_clue_reveals(plot_point)
                print(f"Good [{len(self.plot_points)} accumulated]")
            else:
                print(f"Bad (skipped after {MAX_REGEN_ATTEMPTS} attempts)")
            step += 1

            if step > TARGET_PLOT_POINTS + 10:
                break

        count = len(self.plot_points)
        if count < MIN_PLOT_POINTS:
            raise RuntimeError(
                f"Only generated {count} valid plot points (minimum is {MIN_PLOT_POINTS})"
            )
        print(f"Accumulated {count} plot points.")
        return self.plot_points

    def _generate_one_step(self, step: int) -> str | None:
        arc = _arc_instruction(step, TARGET_PLOT_POINTS)
        context = _build_context_summary(
            self.state, self.plot_points, self.revealed_clues
        )

        for attempt in range(1, MAX_REGEN_ATTEMPTS + 1):
            prompt = self._build_step_prompt(step, arc, context, attempt)
            try:
                raw = call_llm(
                    prompt=prompt,
                    model_name=PLOT_GEN_MODEL,
                    system_instruction=self._system_instruction(),
                    expect_json=False,
                    temperature=PROSE_TEMPERATURE,
                    max_output_tokens=512,
                )
                text = raw.strip()
                result = self.checker.check(text, step)
                if result.is_valid:
                    return text
                else:
                    context = context + f"\n[REJECTED attempt {attempt}: {result.reason}]\n"
            except RuntimeError as exc:
                print(f"(LLM error: {exc})", end="", flush=True)
        return None

    def _build_step_prompt(
        self, step: int, arc: str, context: str, attempt: int
    ) -> str:
        extra = ""
        if attempt > 1:
            extra = (
                f"\nPrevious attempt was rejected. Try a DIFFERENT kind of event "
                f"(different obstacle type, different character focus).\n"
            )

        return f"""\
{context}
=== YOUR TASK ===
You are generating plot point #{step} of {TARGET_PLOT_POINTS} for this murder mystery.

Narrative arc instruction for this step:
{arc}

{extra}Write EXACTLY ONE plot point: a single concrete event that moves the \
investigation forward. Write in third-person past tense, 2–4 sentences. \
Be specific (name characters, locations, objects). Do NOT resolve the mystery \
or name the culprit yet (unless step {TARGET_PLOT_POINTS - 1} or later).

Output ONLY the plot point text. No labels, no numbering, no preamble.
"""

    def _system_instruction(self) -> str:
        return (
            "You are a crime fiction author writing one plot point at a time for "
            "a suspenseful murder mystery. Each plot point is 2–4 sentences, "
            "third-person past tense, vivid and specific. You must reference "
            "characters and clues from the crime world provided. Never contradict "
            "established facts. Never name the killer prematurely."
        )

    def _update_clue_reveals(self, text: str) -> None:
        lower = text.lower()
        for clue in self.state.get("clues", []):
            fingerprint = clue["description"].lower()[:30]
            if fingerprint in lower:
                if clue["id"] not in self.revealed_clues:
                    self.revealed_clues.append(clue["id"])
                    self.checker.mark_clue_discovered(clue["id"])
