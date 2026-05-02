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


@dataclass
class DMDecision:
    action: str        
    message: str        
    log_entry: str      
    modified_state: dict = field(default_factory=dict)
    accommodation_result: str | None = None

class DramaManager:

    def __init__(self, game_state: GameState):
        self.gs = game_state
        self.log: list[str] = []

    def evaluate(
        self,
        action: InterpretedAction,
        execution_result: ExecutionResult | None = None,
    ) -> DMDecision:
        if action.category == ActionCategory.EXCEPTIONAL:
            return self._handle_exception(action)

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
            self.gs.consecutive_non_constituent = max(0, self.gs.consecutive_non_constituent - 1)
        else:
            self.gs.consecutive_non_constituent += 1

        if action_was_productive or action.verb in guidance_verbs:
            return DMDecision(
                action="allow",
                message="",
                log_entry=f"DM: allowed {action.verb} ({action.category.value})",
            )

        if self.gs.consecutive_non_constituent >= HINT_AFTER_N_STUCK:
            return self._give_hint()

        causer = self._check_for_causer()
        if causer:
            return causer

        return DMDecision(
            action="allow",
            message="",
            log_entry=f"DM: allowed {action.verb} ({action.category.value})",
        )

    def get_log(self) -> list[str]:
        return self.log


    def _handle_exception(self, action: InterpretedAction) -> DMDecision:
        self._log(f"EXCEPTION detected: {action.raw_input!r} | "
                  f"Affected links: {action.affected_causal_links}")

        threatened_objects = self._get_threatened_objects(action)

        if not threatened_objects:
            entry = f"DM BLOCKED (no clear threat identified): {action.raw_input!r}"
            self._log(entry)
            return DMDecision(
                action="block",
                message=self._block_message(action),
                log_entry=entry,
            )

        accommodation = self._accommodate(action, threatened_objects)
        if accommodation:
            return accommodation

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
        clue_ids = [o for o in threatened if o.startswith("clue_")]
        if not clue_ids:
            return None

        for attempt in range(MAX_REPAIR_ATTEMPTS):
            repair = self._generate_repair(clue_ids, action)
            if repair:
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
        new_room_id = repair.get("new_clue_location", "")
        new_source  = repair.get("new_clue_source", "")

        for obj in self.gs.objects.values():
            if obj.is_evidence and obj.location in ("destroyed", "removed"):
                if new_room_id and new_room_id in self.gs.rooms:
                    obj.location = new_room_id
                    room = self.gs.rooms[new_room_id]
                    if obj.id not in room.objects:
                        room.objects.append(obj.id)
                    obj.state["damaged"] = True 
                    break

        if new_source:
            for npc in self.gs.npcs.values():
                if new_source.lower() in npc.name.lower():
                    npc.known_facts.append(
                        f"(After the incident) {repair.get('player_message', '')}"
                    )
                    break

    def _get_threatened_objects(self, action: InterpretedAction) -> list[str]:
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


    def _give_hint(self) -> DMDecision:
        self.gs.consecutive_non_constituent = 0
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
        self.log.append(f"[Turn {self.gs.turn_count}] {entry}")


def _ensure_complete_sentence(text: str, fallback: str) -> str:
    text = (text or "").strip()
    if not text:
        return fallback
    if text[-1] not in ".!?\"'”’":
        return fallback
    return text
