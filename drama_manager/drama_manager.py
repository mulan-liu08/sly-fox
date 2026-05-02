"""
drama_manager/drama_manager.py — Template 2: Intervention and Accommodation.

The Drama Manager (DM) sits between the action interpreter and the executor.
It has three responsibilities:

1. EXCEPTION DETECTION
   When the interpreter flags an EXCEPTIONAL action, the DM checks which
   causal links are threatened and decides how to respond.

2. ACCOMMODATION (story repair)
   If a causal link is broken, the DM repairs the story plan so the crime
   can still be solved. This may involve:
     - Moving a clue to a new location (if the original was destroyed)
     - Having an NPC mention a clue in conversation (if evidence is gone)
     - Generating a new path to the same information

3. INTERVENTION (proactive nudging)
   The DM monitors player progress and intervenes when:
     - Player is stuck (N consecutive non-constituent actions)
     - Player is about to shortcut to the ending prematurely
     - A plot point needs to be caused (player missed something important)

All DM decisions are logged for transparency in the demo video.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from llm_client import call_llm
from config import REPAIR_MODEL, REPAIR_TEMP, HINT_AFTER_N_STUCK, MAX_REPAIR_ATTEMPTS
from world.game_state import (
    GameState, ActionCategory, PlotPointStatus, NPCStatus
)
from engine.action_interpreter import InterpretedAction
from engine.action_executor import ExecutionResult, _next_step_hint


# ─── DM decision types ────────────────────────────────────────────────────────

@dataclass
class DMDecision:
    action: str          # "allow" | "block" | "accommodate" | "hint" | "cause"
    message: str         # message to show player (if any)
    log_entry: str       # internal log for demo transparency
    modified_state: dict = field(default_factory=dict)
    accommodation_result: str | None = None


# ─── Main Drama Manager ───────────────────────────────────────────────────────

class DramaManager:
    """
    Intervenes in the player-game loop to maintain story coherence and pacing.
    """

    def __init__(self, game_state: GameState):
        self.gs = game_state
        self.log: list[str] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def evaluate(
        self,
        action: InterpretedAction,
        execution_result: ExecutionResult | None = None,
    ) -> DMDecision:
        """
        Called BEFORE execution for EXCEPTIONAL actions.
        Called AFTER execution for CONSTITUENT/CONSISTENT actions.

        Returns a DMDecision describing what the DM does.
        """
        # ── Pre-execution: exceptional actions ────────────────────────────────
        if action.category == ActionCategory.EXCEPTIONAL:
            return self._handle_exception(action)

        # ── Post-execution: track progress ────────────────────────────────────
        # Deterministic parsing often marks useful game actions as CONSISTENT,
        # so use the executor result as the source of truth for progress.
        made_progress = bool(
            execution_result and (
                execution_result.clue_discovered
                or execution_result.npc_interviewed
                or execution_result.plot_point_executed
                or execution_result.game_won
            )
        )
        productive_verbs = {
            "talk", "interview", "question", "examine", "look", "search",
            "case", "suspects", "evidence", "hint", "accuse", "show",
        }
        guidance_verbs = {"case", "suspects", "evidence", "hint", "help", "map", "inventory"}
        action_was_productive = (
            action.category == ActionCategory.CONSTITUENT
            or made_progress
            or (execution_result and execution_result.success and action.verb in productive_verbs)
        )

        if action_was_productive:
            self.gs.consecutive_non_constituent = 0
        elif execution_result and execution_result.success and action.verb in {"go", "move", "walk", "run"}:
            # Navigation is neutral: it should not instantly trigger hints, but
            # repeated wandering can eventually invite a nudge.
            self.gs.consecutive_non_constituent = max(0, self.gs.consecutive_non_constituent - 1)
        else:
            self.gs.consecutive_non_constituent += 1

        # Suppress unsolicited DM hints after productive or explicit guidance
        # actions. The response itself is already useful, so an extra nudge feels
        # intrusive. Players can still type HINT whenever they want help.
        if action_was_productive or action.verb in guidance_verbs:
            return DMDecision(
                action="allow",
                message="",
                log_entry=f"DM: allowed {action.verb} ({action.category.value})",
            )

        # ── Check if player is stuck ──────────────────────────────────────────
        if self.gs.consecutive_non_constituent >= HINT_AFTER_N_STUCK:
            return self._give_hint()

        # ── Check if a plot point needs to be caused ─────────────────────────
        causer = self._check_for_causer()
        if causer:
            return causer

        # ── Default: allow ────────────────────────────────────────────────────
        return DMDecision(
            action="allow",
            message="",
            log_entry=f"DM: allowed {action.verb} ({action.category.value})",
        )

    def get_log(self) -> list[str]:
        return self.log

    # ── Exception handling ────────────────────────────────────────────────────

    def _handle_exception(self, action: InterpretedAction) -> DMDecision:
        """
        An exceptional action was attempted. Decide: block or accommodate.
        """
        self._log(f"EXCEPTION detected: {action.raw_input!r} | "
                  f"Affected links: {action.affected_causal_links}")

        # Check if the game is still solvable AFTER this action
        # Simulate: temporarily mark affected links as broken
        threatened_objects = self._get_threatened_objects(action)

        if not threatened_objects:
            # The LLM flagged it as exceptional but we can't identify what breaks
            # Be conservative: block it with an explanation
            entry = f"DM BLOCKED (no clear threat identified): {action.raw_input!r}"
            self._log(entry)
            return DMDecision(
                action="block",
                message=self._block_message(action),
                log_entry=entry,
            )

        # Try to accommodate — repair the story around the exception
        accommodation = self._accommodate(action, threatened_objects)
        if accommodation:
            return accommodation

        # Accommodation failed — block the action
        entry = f"DM BLOCKED (accommodation failed): {action.raw_input!r}"
        self._log(entry)
        return DMDecision(
            action="block",
            message=self._block_message(action),
            log_entry=entry,
        )

    def _accommodate(
        self,
        action: InterpretedAction,
        threatened: list[str],
    ) -> DMDecision | None:
        """
        Attempt to repair the story plan so the crime can still be solved
        even if the exceptional action is allowed.

        Strategy:
          1. For each threatened clue, generate an alternative way to reveal
             the same information (another NPC mentions it, a copy exists, etc.)
          2. If repair is possible, allow the action and apply the repair.
          3. If not possible, return None (caller will block).
        """
        clue_ids = [o for o in threatened if o.startswith("clue_")]
        if not clue_ids:
            return None

        for attempt in range(MAX_REPAIR_ATTEMPTS):
            repair = self._generate_repair(clue_ids, action)
            if repair:
                # Apply the repair to the game state
                self._apply_repair(repair)
                entry = (
                    f"DM ACCOMMODATE (attempt {attempt+1}): "
                    f"allowed {action.raw_input!r}, "
                    f"repaired via: {repair['description']}"
                )
                self._log(entry)
                self.gs.accommodations_made.append(entry)
                return DMDecision(
                    action="accommodate",
                    message=repair.get("player_message", ""),
                    log_entry=entry,
                    accommodation_result=repair["description"],
                )

        return None

    def _generate_repair(
        self,
        clue_ids: list[str],
        action: InterpretedAction,
    ) -> dict | None:
        """Use LLM to generate a story repair plan."""
        crime = self.gs.crime_state
        clue_details = [
            c for c in crime.get("clues", []) if c["id"] in clue_ids
        ]
        if not clue_details:
            return None

        npcs = [n.name for n in self.gs.npcs.values()]
        rooms = [r.name for r in self.gs.rooms.values()]

        prompt = (
            "You are a drama manager for a murder mystery text game. "
            "The player just performed an action that would destroy key evidence. "
            "Generate a story repair so the crime can still be solved.\n\n"
            f"Action performed: {action.raw_input}\n"
            f"Evidence at risk:\n"
            + "\n".join(f"  - [{c['id']}] {c['description']}" for c in clue_details)
            + f"\n\nAvailable NPCs: {npcs}\n"
            f"Available rooms: {rooms}\n\n"
            "Generate a repair. Return JSON:\n"
            "{\n"
            '  "description": "what the DM does to repair the story",\n'
            '  "new_clue_location": "room_id where the information can now be found",\n'
            '  "new_clue_source": "npc_name or object_name that now carries this info",\n'
            '  "player_message": "1-2 sentence in-world description of what happens '
            '(e.g. an NPC notices something important)",\n'
            '  "feasible": true\n'
            "}\n"
            "If repair is not feasible, set feasible to false. "
            "Return ONLY the JSON."
        )

        try:
            result = call_llm(
                prompt=prompt,
                model_name=REPAIR_MODEL,
                expect_json=True,
                temperature=REPAIR_TEMP,
                max_output_tokens=512,
            )
            if result.get("feasible", False):
                return result
        except Exception as e:
            self._log(f"DM repair LLM failed: {e}")

        return None

    def _apply_repair(self, repair: dict) -> None:
        """Apply a repair plan to the game state."""
        new_room_id = repair.get("new_clue_location", "")
        new_source  = repair.get("new_clue_source", "")

        # Move any threatened evidence objects to the new location
        for obj in self.gs.objects.values():
            if obj.is_evidence and obj.location in ("destroyed", "removed"):
                if new_room_id and new_room_id in self.gs.rooms:
                    obj.location = new_room_id
                    room = self.gs.rooms[new_room_id]
                    if obj.id not in room.objects:
                        room.objects.append(obj.id)
                    obj.state["damaged"] = True  # flag it was tampered with
                    break

        # If source is an NPC, add the fact to their known_facts
        if new_source:
            for npc in self.gs.npcs.values():
                if new_source.lower() in npc.name.lower():
                    npc.known_facts.append(
                        f"(After the incident) {repair.get('player_message', '')}"
                    )
                    break

    def _get_threatened_objects(self, action: InterpretedAction) -> list[str]:
        """Return ids of objects/clues threatened by this action."""
        threatened = list(action.affected_causal_links)
        target = (action.target or "").lower()
        for obj in self.gs.objects.values():
            if target in obj.name.lower() or target in obj.id.lower():
                if obj.is_evidence:
                    threatened.append(obj.clue_id or obj.id)
        return threatened

    def _block_message(self, action: InterpretedAction) -> str:
        verb = action.verb
        if verb in ("destroy", "break", "damage"):
            return (
                "Something stops you. This is an active crime scene — "
                "destroying evidence could obstruct justice and compromise your investigation."
            )
        if verb in ("kill", "attack"):
            return (
                "You're a detective, not an assailant. "
                "Attacking a witness or suspect would end your investigation immediately."
            )
        return (
            f"You reconsider. Taking that action could make it impossible to "
            f"solve the crime. Better to proceed more carefully."
        )

    # ── Proactive intervention ────────────────────────────────────────────────

    def _give_hint(self) -> DMDecision:
        """Player is stuck — give a subtle in-world atmospheric nudge, not explicit navigation."""
        self.gs.consecutive_non_constituent = 0
        # Use _generate_hint for an atmospheric, non-spoilery nudge.
        # _next_step_hint gives explicit "go north, go east" instructions which
        # go stale as the player moves and break immersion.
        available_pps = self.gs.get_available_plot_points()
        if available_pps:
            pp = available_pps[0]
            hint = self._generate_hint(pp.description, pp.location_hint)
        else:
            hint = "A quiet instinct tells you there is still more to uncover here."
        entry = f"DM HINT: {hint[:80]}"
        self._log(entry)
        self.gs.active_hints.append(hint)
        return DMDecision(action="hint", message=hint, log_entry=entry)

    def _generate_hint(self, plot_point_desc: str, location_hint: str) -> str:
        """Generate an in-world hint without breaking the fourth wall."""
        room_name = self.gs.rooms.get(location_hint, None)
        room_str = room_name.name if room_name else location_hint.replace("_", " ")

        prompt = (
            "Generate a subtle, in-world hint for a detective in a murder mystery. "
            "The hint should nudge them toward the next clue without being obvious. "
            "Write 1-2 sentences in atmospheric prose. Do NOT break the fourth wall. "
            f"Next clue area: {plot_point_desc}\n"
            f"Location hint: {room_str}\n"
            "The hint might come as: a gut feeling, a remembered detail, "
            "a sound from another room, or a colleague saying something vague. "
            "Output only the hint text."
        )
        fallback = f"Something tells you there may be more to discover in the {room_str}."
        try:
            hint = call_llm(
                prompt=prompt,
                model_name=REPAIR_MODEL,
                temperature=0.8,
                max_output_tokens=512,
            ).strip()
            return _ensure_complete_sentence(hint, fallback)
        except Exception:
            return fallback

    def _check_for_causer(self) -> DMDecision | None:
        """Offer a proactive nudge at pacing intervals.

        Earlier versions logged this as "auto-advancing" a plot point even
        though it did not actually discover a clue. That was confusing in the
        debug output and misleading for the demo. This now behaves as a visible
        intervention/hint only.
        """
        if self.gs.turn_count % 8 != 0 or self.gs.turn_count == 0:
            return None

        cause_msg = _next_step_hint(self.gs)
        if cause_msg:
            entry = f"DM CAUSER: proactive guidance — {cause_msg[:80]}"
            self._log(entry)
            self.gs.active_hints.append(cause_msg)
            return DMDecision(
                action="cause",
                message=cause_msg,
                log_entry=entry,
            )
        return None

    def _generate_causer_event(self, pp) -> str | None:
        """Generate an in-world event that nudges the player toward a plot point."""
        try:
            prompt = (
                "Generate a brief in-world event (1 sentence) that naturally draws "
                "the detective's attention toward a specific area of investigation. "
                f"Target investigation: {pp.description}\n"
                "The event could be: a colleague mentioning something odd, "
                "a distant sound, or a notification on the detective's device. "
                "Keep it subtle and atmospheric. Output only the event text."
            )
            event = call_llm(
                prompt=prompt,
                model_name=REPAIR_MODEL,
                temperature=0.8,
                max_output_tokens=512,
            ).strip()
            return _ensure_complete_sentence(
                event,
                "A distant sound pulls your attention back to the investigation.",
            )
        except Exception:
            return None

    def _log(self, entry: str) -> None:
        # Keep the log for --debug and saved game logs. Do not print here,
        # because game.py already prints DM decisions in debug mode.
        self.log.append(f"[Turn {self.gs.turn_count}] {entry}")


def _ensure_complete_sentence(text: str, fallback: str) -> str:
    """Avoid printing visibly truncated LLM hints/events."""
    text = (text or "").strip()
    if not text:
        return fallback
    if text[-1] not in ".!?\"'”’":
        return fallback
    return text
