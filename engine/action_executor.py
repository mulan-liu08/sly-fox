"""
engine/action_executor.py — Executes interpreted actions against the GameState.

Handles all CONSTITUENT and CONSISTENT actions.
EXCEPTIONAL actions are handed to the drama manager before execution.

Returns an ExecutionResult with:
  - success: bool
  - state_changes: what changed in the world
  - narrative_hint: short description for the response generator
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

import re

from world.game_state import (
    GameState, ActionCategory, PlotPointStatus, NPCStatus, ClueStatus
)
from engine.action_interpreter import InterpretedAction


@dataclass
class ExecutionResult:
    success: bool
    state_changes: dict[str, Any] = field(default_factory=dict)
    narrative_hint: str = ""
    plot_point_executed: str | None = None
    clue_discovered: str | None = None
    npc_interviewed: str | None = None
    game_over: bool = False
    game_won: bool = False


# ─── Main executor ────────────────────────────────────────────────────────────

def execute_action(
    action: InterpretedAction,
    gs: GameState,
) -> ExecutionResult:
    """
    Execute a CONSTITUENT or CONSISTENT action.
    EXCEPTIONAL actions should be intercepted by drama manager first.
    """
    verb = action.verb

    # ── Navigation ────────────────────────────────────────────────────────────
    if verb in ("move", "go", "walk", "run"):
        return _do_move(action, gs)

    # ── Observation ───────────────────────────────────────────────────────────
    if verb in ("examine", "look", "inspect", "read", "smell", "touch"):
        return _do_examine(action, gs)

    if verb == "search":
        return _do_search(action, gs)

    if verb == "inventory":
        return _do_inventory(gs)

    if verb == "map":
        return _do_map(gs)

    if verb == "exits":
        return _do_exits(gs)

    if verb in ("case", "notebook"):
        return _do_case_board(gs)

    if verb in ("evidence", "clues"):
        return _do_evidence(gs)

    if verb == "suspects":
        return _do_suspects(gs)

    if verb == "hint":
        return _do_hint(gs)

    # ── Inventory ─────────────────────────────────────────────────────────────
    if verb in ("take", "pick_up", "grab"):
        return _do_take(action, gs)

    if verb in ("drop", "put_down"):
        return _do_drop(action, gs)

    # ── Social / location questions ──────────────────────────────────────────
    if verb == "ask":
        investigation_answer = _answer_investigation_question(action, gs)
        if investigation_answer is not None:
            return investigation_answer
        loc_answer = _answer_location_question(action, gs)
        if loc_answer is not None:
            return loc_answer
        return _do_talk(action, gs)

    if verb in ("talk", "interview", "question"):
        return _do_talk(action, gs)

    if verb == "show":
        return _do_show(action, gs)

    if verb == "accuse":
        return _do_accuse(action, gs)

    # ── Object interaction ────────────────────────────────────────────────────
    if verb in ("use", "open", "unlock"):
        return _do_use(action, gs)

    # ── Notes ─────────────────────────────────────────────────────────────────
    if verb in ("note", "record"):
        return _do_note(action, gs)

    # ── Wait ─────────────────────────────────────────────────────────────────
    if verb in ("wait", "rest"):
        return ExecutionResult(
            success=True,
            narrative_hint="Time passes. The hum of the facility continues.",
        )

    # ── Help ─────────────────────────────────────────────────────────────────
    if verb == "help":
        return _do_help()

    # ── Unknown ───────────────────────────────────────────────────────────────
    return ExecutionResult(
        success=False,
        narrative_hint=f"You consider trying to '{action.raw_input}' but aren't sure how.",
    )


# ─── Action implementations ───────────────────────────────────────────────────

def _do_move(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    current_room = gs.rooms.get(gs.player.location)
    if not current_room:
        return ExecutionResult(False, narrative_hint="You're not sure where you are.")

    target = (action.target or "").lower().strip()
    if not target:
        return ExecutionResult(False, narrative_hint="exits:" + _available_exits_text(gs))

    dest_id = _resolve_exit_target(current_room, target, gs)

    if not dest_id or dest_id not in gs.rooms:
        return ExecutionResult(
            False,
            narrative_hint=f"You can't go that way. {_available_exits_text(gs)}",
        )

    gs.player.location = dest_id
    dest_room = gs.rooms[dest_id]
    was_visited = dest_room.visited
    dest_room.visited = True

    return ExecutionResult(
        success=True,
        state_changes={"location": dest_id, "was_visited": was_visited},
        narrative_hint=f"room:{dest_id}:{'visited' if was_visited else 'new'}",
    )


def _do_examine(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    target = (action.target or "").lower().strip()

    # Examining the room itself
    if not target or target in ("room", "around", "area", "here", "surroundings"):
        room = gs.rooms.get(gs.player.location)
        if room:
            room.visited = True
        return ExecutionResult(
            success=True,
            narrative_hint="examine_room",  # signal to response gen to describe room
        )

    if target in ("exits", "ways out", "where can i go", "where to go"):
        return _do_exits(gs)

    # Asking who/what is in the current room should describe the room, not
    # look for an object literally named "people".
    if target in (
        "people", "person", "persons", "npc", "npcs", "anyone",
        "someone", "who", "occupants", "characters", "witnesses",
    ):
        room = gs.rooms.get(gs.player.location)
        if room:
            room.visited = True
        return ExecutionResult(
            success=True,
            narrative_hint="room:" + gs.player.location,
        )

    # Some generated worlds create interaction-like exits such as
    # "examine_desk → autopsy_report". Treat "examine desk" as following that
    # interaction, so players do not have to type "go to examine_desk".
    pseudo_move = _follow_interaction_exit(target, gs)
    if pseudo_move is not None:
        return pseudo_move

    # Find object by name or id
    obj = _find_object(target, gs)
    if obj:
        obj.state["examined"] = True
        clue_found = None
        if obj.is_evidence and obj.clue_id not in gs.player.discovered_clues:
            # Discover the clue
            gs.player.discovered_clues.append(obj.clue_id)
            clue_found = obj.clue_id
            gs.mark_plot_point_done(obj.clue_id)
            # Unlock any clues that had this as prerequisite
            _unlock_dependent_clues(obj.clue_id, gs)
            return ExecutionResult(
                success=True,
                state_changes={"examined": obj.id, "clue_discovered": obj.clue_id},
                narrative_hint=f"examine_object:{obj.id}",
                clue_discovered=clue_found,
                plot_point_executed=obj.clue_id,
            )
        return ExecutionResult(
            success=True,
            state_changes={"examined": obj.id},
            narrative_hint=f"examine_object:{obj.id}",
        )

    # Find NPC
    npc = _find_npc(target, gs)
    if npc:
        return ExecutionResult(
            success=True,
            narrative_hint=f"examine_npc:{npc.id}",
        )

    return ExecutionResult(
        False,
        narrative_hint=f"You don't see '{target}' here.",
    )


def _do_search(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    """Thorough search of current room — may reveal hidden objects."""
    room = gs.rooms.get(gs.player.location)
    if not room:
        return ExecutionResult(False, narrative_hint="Nothing to search here.")

    # Reveal hidden objects whose prerequisite clues have been found
    revealed = []
    for obj_id, obj in gs.objects.items():
        if obj.location.startswith("hidden_") and obj.clue_id:
            room_part = obj.location.replace("hidden_", "")
            if room_part == gs.player.location or room_part in gs.player.location:
                prereq_id = None
                for clue in gs.crime_state.get("clues", []):
                    if clue["id"] == obj.clue_id:
                        prereq_id = clue.get("prerequisite_clue_id")
                        break
                if prereq_id and prereq_id in gs.player.discovered_clues:
                    obj.location = gs.player.location
                    if obj_id not in room.objects:
                        room.objects.append(obj_id)
                    revealed.append(obj.name)

    if revealed:
        return ExecutionResult(
            success=True,
            state_changes={"revealed_objects": revealed},
            narrative_hint=f"search_reveals:{','.join(revealed)}",
        )
    return ExecutionResult(
        success=True,
        narrative_hint="search_nothing_new",
    )


def _do_inventory(gs: GameState) -> ExecutionResult:
    items = [gs.objects[oid].name for oid in gs.player.inventory if oid in gs.objects]
    hint = "inventory:" + (", ".join(items) if items else "empty")
    return ExecutionResult(success=True, narrative_hint=hint)


def _do_map(gs: GameState) -> ExecutionResult:
    lines = ["Known locations:"]
    for room in gs.rooms.values():
        if room.visited or room.id == gs.player.location:
            marker = " ← YOU ARE HERE" if room.id == gs.player.location else ""
            exits = ", ".join(f"{_display_exit_label(d)}→{r}" for d, r in room.exits.items())
            lines.append(f"  {room.name}{marker}  [{exits}]")
    return ExecutionResult(success=True, narrative_hint="map:" + "\n".join(lines))


def _do_exits(gs: GameState) -> ExecutionResult:
    return ExecutionResult(success=True, narrative_hint="exits:" + _available_exits_text(gs))


def _do_case_board(gs: GameState) -> ExecutionResult:
    return ExecutionResult(success=True, narrative_hint="case:" + _case_board_text(gs))


def _do_evidence(gs: GameState) -> ExecutionResult:
    return ExecutionResult(success=True, narrative_hint="evidence:" + _evidence_text(gs))


def _do_suspects(gs: GameState) -> ExecutionResult:
    return ExecutionResult(success=True, narrative_hint="suspects:" + _suspect_text(gs))


def _do_hint(gs: GameState) -> ExecutionResult:
    return ExecutionResult(success=True, narrative_hint="hint:" + _next_step_hint(gs))


def _do_take(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    target = (action.target or "").lower().strip()
    obj = _find_object(target, gs)
    if not obj:
        return ExecutionResult(False, narrative_hint=f"You don't see '{target}' to take.")
    if obj.location == "inventory":
        return ExecutionResult(False, narrative_hint=f"You already have the {obj.name}.")
    if obj.is_evidence:
        return ExecutionResult(
            success=True,
            narrative_hint=(
                f"case_answer:You make a careful note of the {obj.name}, but leave it preserved at the scene. "
                f"To log it as evidence, examine the {obj.name}."
            ),
        )
    obj.location = "inventory"
    obj.state["taken"] = True
    gs.player.inventory.append(obj.id)
    room = gs.rooms.get(gs.player.location)
    if room and obj.id in room.objects:
        room.objects.remove(obj.id)
    return ExecutionResult(
        success=True,
        state_changes={"taken": obj.id},
        narrative_hint=f"take:{obj.name}",
    )


def _do_drop(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    target = (action.target or "").lower().strip()
    obj = _find_object_in_inventory(target, gs)
    if not obj:
        return ExecutionResult(False, narrative_hint=f"You don't have '{target}'.")
    obj.location = gs.player.location
    obj.state["taken"] = False
    gs.player.inventory.remove(obj.id)
    room = gs.rooms.get(gs.player.location)
    if room and obj.id not in room.objects:
        room.objects.append(obj.id)
    return ExecutionResult(
        success=True,
        state_changes={"dropped": obj.id},
        narrative_hint=f"drop:{obj.name}",
    )


def _do_talk(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    target = (action.target or "").lower().strip()
    npc = _find_npc(target, gs)
    if not npc:
        return ExecutionResult(False, narrative_hint=f"You don't see '{target}' here to talk to.")

    # Mark as interviewed
    was_interviewed = npc.id in gs.player.interviewed_npcs
    if not was_interviewed:
        npc.status = NPCStatus.INTERVIEWED
        gs.player.interviewed_npcs.append(npc.id)
        gs.mark_plot_point_done(f"interview_{npc.id}")

    # Gather what the NPC will say
    revealed_facts = list(npc.known_facts)
    for req_clue_id, fact in npc.locked_facts:
        if req_clue_id in gs.player.discovered_clues:
            revealed_facts.append(fact)

    hint = f"talk:{npc.id}:{npc.name}:{npc.alibi}"
    if revealed_facts:
        hint += ":" + " | ".join(revealed_facts[:2])

    return ExecutionResult(
        success=True,
        state_changes={"interviewed": npc.id},
        narrative_hint=hint,
        npc_interviewed=npc.id if not was_interviewed else None,
        plot_point_executed=f"interview_{npc.id}" if not was_interviewed else None,
    )


def _do_show(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    """Show an object from inventory to an NPC."""
    obj_target = (action.target or "").lower().strip()
    npc_target = (action.secondary or "").lower().strip()

    obj = _find_object_in_inventory(obj_target, gs)
    if not obj:
        return ExecutionResult(False, narrative_hint=f"You don't have '{obj_target}' to show.")

    npc = _find_npc(npc_target, gs)
    if not npc:
        return ExecutionResult(False, narrative_hint=f"You don't see '{npc_target}' to show it to.")

    # Check if this object unlocks a locked fact for this NPC
    unlocked = []
    for req_clue_id, fact in npc.locked_facts:
        if obj.clue_id == req_clue_id or obj.id == req_clue_id:
            unlocked.append(fact)

    hint = f"show:{obj.id}:{npc.id}:{npc.name}"
    if unlocked:
        hint += ":reveals:" + unlocked[0]
        if obj.clue_id and obj.clue_id not in gs.player.discovered_clues:
            gs.player.discovered_clues.append(obj.clue_id)

    return ExecutionResult(
        success=True,
        narrative_hint=hint,
    )


def _do_accuse(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    target = (action.target or "").lower().strip()
    from config import MIN_CLUES_TO_ACCUSE

    if len(gs.player.discovered_clues) < MIN_CLUES_TO_ACCUSE:
        return ExecutionResult(
            False,
            narrative_hint=f"accuse_too_early:{len(gs.player.discovered_clues)}/{MIN_CLUES_TO_ACCUSE}",
        )

    culprit_name = gs.crime_state.get("culprit", {}).get("name", "").lower()
    npc = _find_npc(target, gs)
    if not npc:
        # Check by name fragment
        accused_name = target
        if culprit_name and (accused_name in culprit_name or culprit_name in accused_name):
            gs.game_won = True
            gs.game_over = True
            return ExecutionResult(
                success=True,
                state_changes={"game_won": True},
                narrative_hint=f"accuse_correct:{culprit_name}",
                game_won=True, game_over=True,
            )
        return ExecutionResult(
            False,
            narrative_hint=f"wrong_accusation:{target}",
        )

    if npc.is_culprit:
        if npc.id not in gs.player.interviewed_npcs:
            return ExecutionResult(
                False,
                narrative_hint=(
                    f"case_answer:{npc.name} is the strongest current lead, but you should confront them before making the final accusation. "
                    f"Find and talk to {npc.name}, then accuse them if their story still does not hold together."
                ),
            )
        gs.game_won = True
        gs.game_over = True
        gs.mark_plot_point_done("reveal_culprit")
        return ExecutionResult(
            success=True,
            state_changes={"game_won": True},
            narrative_hint=f"accuse_correct:{npc.name}",
            game_won=True, game_over=True,
            plot_point_executed="reveal_culprit",
        )
    else:
        return ExecutionResult(
            False,
            narrative_hint=f"accuse_wrong:{npc.name}",
        )


def _do_use(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    target = (action.target or "").lower().strip()
    obj = _find_object(target, gs) or _find_object_in_inventory(target, gs)
    if not obj:
        return ExecutionResult(False, narrative_hint=f"You can't find '{target}' to use.")
    return ExecutionResult(
        success=True,
        narrative_hint=f"use:{obj.id}:{obj.name}",
    )


def _do_note(action: InterpretedAction, gs: GameState) -> ExecutionResult:
    note_text = action.target or action.raw_input
    gs.player.notes.append(note_text)
    return ExecutionResult(
        success=True,
        narrative_hint=f"note_added:{note_text[:50]}",
    )


def _do_help() -> ExecutionResult:
    help_text = (
        "help:Core commands:\n"
        "  go [direction/room], examine [object], search, take [object]\n"
        "  talk to [person], show [object] to [person], accuse [person]\n"
        "  evidence, suspects, case, hint, inventory, map, note [text]\n"
        "Tip: once you have enough evidence, type CASE or SUSPECTS to decide who to accuse. "
        "Then use: accuse [suspect name]."
    )
    return ExecutionResult(success=True, narrative_hint=help_text)



# ─── Case-board / guidance helpers ───────────────────────────────────────────

def _evidence_name(clue_id: str, gs: GameState) -> str:
    obj = next((o for o in gs.objects.values() if o.clue_id == clue_id), None)
    return obj.name if obj else clue_id.replace("_", " ")


def _clue_by_id(clue_id: str, gs: GameState) -> dict | None:
    return next((c for c in gs.crime_state.get("clues", []) if c.get("id") == clue_id), None)


def _clue_implication_reason(clue: dict, gs: GameState) -> str:
    """
    Explain why a clue is associated with a specific suspect.
    Uses the suspect's actual crime-state profile rather than keyword guessing.
    """
    points = clue.get("points_to")
    if not points or points == "culprit":
        return ""

    desc = str(clue.get("description", "")).lower()
    is_red_herring = clue.get("is_red_herring", False)
    rh_explanation = clue.get("red_herring_explanation", "")

    # Find the suspect's crime state data
    suspect = next(
        (s for s in gs.crime_state.get("suspects", []) if s.get("name") == points),
        None
    )
    if not suspect:
        return f"It raises questions about {points}."

    relationship = (suspect.get("relationship_to_victim") or "").strip()
    occupation   = (suspect.get("occupation") or "").strip()
    missing      = (suspect.get("missing_element") or "").strip()
    victim       = _victim_short(gs)

    # Check if the description directly mentions the suspect's name
    name_tokens = [t for t in re.findall(r"[a-zA-Z]{4,}", points.lower())]
    names_in_desc = any(t in desc for t in name_tokens)

    if names_in_desc:
        base = f"The evidence directly names or references {points}"
    elif relationship:
        # Keep relationship short — first sentence only
        short_rel = relationship.split(".")[0].rstrip(",")
        base = f"Given {points}'s role ({short_rel}), this object's presence is notable"
    elif occupation:
        base = f"This is consistent with {points}'s position as {occupation}"
    else:
        base = f"This raises questions about {points}'s presence near the scene"

    if is_red_herring:
        return (f"{base}, though further investigation will show this is circumstantial. "
                f"What appears to implicate them has an innocent explanation.")
    else:
        missing_note = ""
        if missing == "means":
            missing_note = f" You still need to establish how {points} could have committed the crime."
        elif missing == "opportunity":
            missing_note = f" You still need to place {points} at the scene during the critical window."
        elif missing == "motive":
            missing_note = f" You still need a concrete reason why {points} would want {victim} dead."
        return f"{base}.{missing_note}"


def _culprit_clue_reason(clue: dict, gs: GameState) -> str:
    """
    Explain culprit-pointing evidence using the actual crime state facts.
    Avoids heuristic keyword guessing — instead maps the clue description
    against what the crime state says about means, method, and opportunity.
    """
    culprit_data = gs.crime_state.get("culprit", {})
    culprit = culprit_data.get("name", "the culprit")
    victim = _victim_short(gs)
    desc = clue.get("description", "").lower()

    means       = (culprit_data.get("means", "") or "").lower()
    method      = (culprit_data.get("method", "") or "").lower()
    opportunity = (culprit_data.get("opportunity", "") or "").lower()
    motive      = (culprit_data.get("motive", "") or "").lower()

    # Check which dimension of the crime state this clue description overlaps with.
    # Use word overlap rather than heuristic keyword lists.
    desc_words  = {w for w in re.findall(r"[a-zA-Z]{4,}", desc)}
    means_words = {w for w in re.findall(r"[a-zA-Z]{4,}", means)}
    method_words = {w for w in re.findall(r"[a-zA-Z]{4,}", method)}
    opp_words   = {w for w in re.findall(r"[a-zA-Z]{4,}", opportunity)}
    mot_words   = {w for w in re.findall(r"[a-zA-Z]{4,}", motive)}

    if desc_words & method_words:
        short_method = method[:80].rstrip(",. ") if method else "the murder method"
        return (f"This connects to how {victim} was killed: it is consistent with "
                f"{culprit}'s method and warrants closer scrutiny of their access.")
    if desc_words & means_words:
        return (f"This connects to the means available to {culprit}: "
                f"the evidence is consistent with their known access and capabilities.")
    if desc_words & opp_words:
        return (f"This bears on opportunity: it helps place {culprit} "
                f"near the victim during the critical window.")
    if desc_words & mot_words:
        return (f"This is relevant to motive: it connects to why {culprit} "
                f"may have wanted {victim} dead.")
    # Fallback: no strong overlap — state neutrally that this warrants investigation
    return (f"This physical evidence warrants attention: it has not been "
            f"fully accounted for and connects to {culprit}'s profile.")


def _culprit_suspect_reason(clue: dict, clue_name: str, culprit_name: str, gs: GameState) -> str:
    text = (clue.get("description", "") + " " + clue_name).lower()
    if _looks_like_motive(text):
        return f"{clue_name} gives {culprit_name} a clearer motive thread"
    if _looks_like_weapon(text):
        return f"{clue_name} looks like means or a delivery mechanism connected to {culprit_name}"
    if _looks_like_body_or_method(text):
        return f"{clue_name} clarifies the murder method and pressures {culprit_name}'s alibi"
    return f"{clue_name} fits the hidden method or motive connected to {culprit_name}"


def _evidence_text(gs: GameState) -> str:
    if not gs.player.discovered_clues:
        return "No evidence has been logged yet. Explore rooms, examine suspicious objects, and talk to suspects."

    lines = ["Evidence logged:"]
    for i, clue_id in enumerate(gs.player.discovered_clues, 1):
        clue = _clue_by_id(clue_id, gs)
        name = _evidence_name(clue_id, gs)
        if not clue:
            lines.append(f"{i}. {name}")
            continue
        marker = "strong case evidence" if not clue.get("is_red_herring") else "circumstantial lead"
        points = clue.get("points_to")
        points_line = ""
        if points == "culprit":
            points_line = " " + _culprit_clue_reason(clue, gs)
        elif points:
            points_line = f" {_clue_implication_reason(clue, gs)}"
        lines.append(f"{i}. {name} — {marker}. {clue.get('description', '')}{points_line}")
    return "\n".join(lines)


def _suspect_text(gs: GameState) -> str:
    scores, reasons = _suspect_scores(gs)
    lines = ["Suspect board:"]
    for npc in sorted(gs.npcs.values(), key=lambda n: scores.get(n.name, 0), reverse=True):
        score = scores.get(npc.name, 0)
        reason_list = reasons.get(npc.name, [])
        reason = "; ".join(reason_list[:3]) if reason_list else "no direct evidence logged yet"
        interviewed = "interviewed" if npc.id in gs.player.interviewed_npcs else "not interviewed"
        lines.append(f"- {npc.name} ({interviewed}): suspicion {score}/5 — {reason}.")
    if len(gs.player.discovered_clues) >= _min_clues_to_accuse():
        lead = _strongest_suspect(gs)
        lines.append("")
        lines.append(f"You have enough evidence to accuse. Strongest current lead: {lead}.")
        lines.append(f"Try: accuse {lead}")
    else:
        lines.append(f"Find {_min_clues_to_accuse() - len(gs.player.discovered_clues)} more clue(s) before accusing anyone.")
    return "\n".join(lines)


def _case_board_text(gs: GameState) -> str:
    lines = ["Detective's case board", "", _evidence_text(gs), "", _suspect_text(gs), "", "Suggested next step:", _next_step_hint(gs)]
    return "\n".join(lines)


def _min_clues_to_accuse() -> int:
    from config import MIN_CLUES_TO_ACCUSE
    return MIN_CLUES_TO_ACCUSE


def _suspect_scores(gs: GameState) -> tuple[dict[str, int], dict[str, list[str]]]:
    scores = {npc.name: 0 for npc in gs.npcs.values()}
    reasons = {npc.name: [] for npc in gs.npcs.values()}
    culprit_name = gs.crime_state.get("culprit", {}).get("name", "")

    for clue_id in gs.player.discovered_clues:
        clue = _clue_by_id(clue_id, gs)
        if not clue:
            continue
        clue_name = _evidence_name(clue_id, gs)
        points = clue.get("points_to")
        if points == "culprit" and culprit_name in scores:
            scores[culprit_name] += 2
            reasons[culprit_name].append(_culprit_suspect_reason(clue, clue_name, culprit_name, gs))
        elif points in scores:
            delta = 1 if clue.get("is_red_herring") else 2
            scores[points] += delta
            reasons[points].append(f"{clue_name} raises questions about this suspect")

        # Only use explicit name mentions as a weak extra signal for non-culprit
        # clues. Do not substring-match short nicknames like "Mac" inside words
        # such as "machined", and do not let culprit clues accidentally implicate
        # unrelated suspects through tool/occupation words.
        if points != "culprit":
            desc = (clue.get("description", "") + " " + clue_name).lower()
            for npc in gs.npcs.values():
                name_tokens = [p.lower().strip(".'\"") for p in npc.name.replace('"', '').split()]
                meaningful = [p for p in name_tokens if len(p) >= 4]
                full = re.escape(npc.name.lower().replace('"', ''))
                explicit = any(re.search(r"\b" + re.escape(part) + r"\b", desc) for part in meaningful)
                if explicit or re.search(r"\b" + full + r"\b", desc):
                    scores[npc.name] += 1
                    reasons[npc.name].append(f"{clue_name} names or implies this suspect")

    # Means/motive/opportunity completeness is useful detective reasoning.
    for npc in gs.npcs.values():
        if npc.is_culprit:
            if gs.player.discovered_clues:
                reasons[npc.name].append("has a complete means/motive/opportunity profile")
                scores[npc.name] = min(5, scores[npc.name] + 1)
        elif npc.is_cleared:
            scores[npc.name] = max(0, scores[npc.name] - 2)
    return scores, reasons


def _strongest_suspect(gs: GameState) -> str:
    scores, _ = _suspect_scores(gs)
    if not scores:
        return "the most suspicious suspect"
    return max(scores, key=lambda name: scores[name])


def _next_step_hint(gs: GameState) -> str:
    if len(gs.player.discovered_clues) >= _min_clues_to_accuse():
        lead = _strongest_suspect(gs)
        return (
            f"You have enough evidence to make an accusation. Review CASE or SUSPECTS if needed, "
            f"then try: accuse {lead}."
        )

    # Prefer visible, undiscovered evidence in the current room.
    room = gs.rooms.get(gs.player.location)
    if room:
        for oid in room.objects:
            obj = gs.objects.get(oid)
            if obj and obj.is_evidence and obj.clue_id not in gs.player.discovered_clues:
                return f"Something here matters. Examine the {obj.name}."

    # Otherwise route to the nearest available, undiscovered evidence.
    target_obj = _next_available_evidence(gs)
    if target_obj:
        route = _route_to_room(gs, target_obj.location)
        room_name = gs.rooms.get(target_obj.location).name if target_obj.location in gs.rooms else target_obj.location
        if route:
            return f"Next lead: {_route_steps_text(route)} to reach {room_name}, then examine the {target_obj.name}."
        return f"Next lead: examine the {target_obj.name} in {room_name}."

    return "Talk to remaining suspects, search rooms you have not searched, or type CASE to review the investigation."


def _next_available_evidence(gs: GameState):
    for obj in gs.objects.values():
        if not obj.is_evidence or obj.clue_id in gs.player.discovered_clues:
            continue
        if obj.location in gs.rooms:
            return obj
    return None


def _route_to_room(gs: GameState, dest_id: str) -> list[str] | None:
    if dest_id == gs.player.location:
        return []
    from collections import deque
    queue = deque([(gs.player.location, [])])
    seen = {gs.player.location}
    while queue:
        rid, path = queue.popleft()
        room = gs.rooms.get(rid)
        if not room:
            continue
        for direction, nxt in room.exits.items():
            if nxt in seen or nxt not in gs.rooms:
                continue
            if nxt == dest_id:
                return path + [direction]
            seen.add(nxt)
            queue.append((nxt, path + [direction]))
    return None


def _route_steps_text(route: list[str]) -> str:
    """Return player-facing route text without exposing internal labels like to_desk."""
    if not route:
        return ""
    steps = []
    for direction in route:
        label = _display_exit_label(direction)
        if label in {"north", "south", "east", "west", "northeast", "northwest", "southeast", "southwest", "up", "down"}:
            steps.append(f"go {label}")
        else:
            steps.append(f"go {label}")
    return ", then ".join(steps)


def _victim_short(gs: GameState) -> str:
    victim_name = gs.crime_state.get("victim", {}).get("name", "the victim")
    parts = [p.strip(",") for p in victim_name.split() if p]
    if len(parts) >= 2 and parts[0].lower() in {"dr.", "dr", "lord", "lady", "sir", "madam", "mr.", "mr", "mrs.", "mrs", "ms.", "ms"}:
        return f"{parts[0]} {parts[-1]}"
    return parts[-1] if parts else "the victim"


def _looks_like_motive(text: str) -> bool:
    return any(w in text for w in ("journal", "diary", "letter", "note", "motive", "blackmail", "fraud", "will", "inheritance", "threat", "secret", "debt", "affair", "algorithm"))


def _looks_like_weapon(text: str) -> bool:
    return any(w in text for w in ("weapon", "knife", "gun", "pistol", "revolver", "rope", "canister", "nozzle", "gauge", "needle", "vial", "bottle", "poison", "toxin", "dart", "syringe"))


def _looks_like_body_or_method(text: str) -> bool:
    return any(w in text for w in ("wound", "puncture", "bruise", "mark", "residue", "blood", "autopsy", "body", "cause of death"))


def _overlaps(text: str, other: str) -> bool:
    tokens = {t for t in re.findall(r"[a-zA-Z]{4,}", text.lower())}
    other_tokens = {t for t in re.findall(r"[a-zA-Z]{4,}", (other or "").lower())}
    return bool(tokens & other_tokens)


def _display_exit_label(direction: str) -> str:
    return direction.replace("_", " ").strip()


def _exit_command_variants(direction: str, dest_name: str | None = None, dest_id: str | None = None) -> set[str]:
    labels = {direction, direction.replace("_", " ")}
    if dest_name:
        labels.add(dest_name)
    if dest_id:
        labels.add(dest_id)
        labels.add(dest_id.replace("_", " "))
    expanded = set()
    for label in list(labels):
        low = label.lower().strip()
        expanded.add(low)
        for prefix in ("to ", "through ", "into ", "back to "):
            if low.startswith(prefix):
                expanded.add(low[len(prefix):].strip())
        expanded.add("go " + low)
        expanded.add("go to " + low)
        expanded.add("go through " + low)
        expanded.add("enter " + low)
    return expanded


def _resolve_exit_target(room, target: str, gs: GameState) -> str | None:
    norm_target = _normalize(target)
    if not norm_target:
        return None
    for direction, room_id in room.exits.items():
        dest = gs.rooms.get(room_id)
        dest_name = dest.name if dest else room_id.replace("_", " ").title()
        variants = _exit_command_variants(direction, dest_name, room_id)
        norm_variants = {_normalize(v) for v in variants if v}
        if norm_target in norm_variants:
            return room_id
        # Allow a player to type just the meaningful part of a special exit:
        # "lab back entrance" should match "to_lab_back_entrance".
        norm_dir = _normalize(direction)
        for prefix in ("to", "through", "into", "backto"):
            if norm_dir.startswith(prefix) and norm_target == norm_dir[len(prefix):]:
                return room_id
        if norm_target and (norm_target in norm_dir or norm_dir in norm_target):
            return room_id
        if dest and norm_target in _normalize(dest.name):
            return room_id
    return None


def _available_exits_text(gs: GameState) -> str:
    room = gs.rooms.get(gs.player.location)
    if not room or not room.exits:
        return "There are no obvious exits."
    parts = []
    for direction, room_id in room.exits.items():
        dest = gs.rooms.get(room_id)
        dest_name = dest.name if dest else room_id.replace("_", " ").title()
        label = _display_exit_label(direction)
        parts.append(f"{label} to {dest_name}")
    return "From here, you can go " + "; ".join(parts) + "."

def _answer_investigation_question(action: InterpretedAction, gs: GameState) -> ExecutionResult | None:
    target = (action.target or "").lower()
    if not target:
        return None
    if any(term in target for term in ("cause of death", "death", "killed", "murder weapon", "method")):
        if gs.player.discovered_clues:
            return ExecutionResult(True, narrative_hint=(
                "case_answer:The first impression is no longer enough. The evidence you have logged points toward a deliberate method; use CASE to connect the method, motive, and opportunity."
            ))
        return ExecutionResult(True, narrative_hint=(
            "case_answer:The official first impression is uncertain. Look for physical evidence before trusting the surface explanation."
        ))
    return None


# ─── Location / generated-interaction helpers ────────────────────────────────

def _normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _follow_interaction_exit(target: str, gs: GameState) -> ExecutionResult | None:
    room = gs.rooms.get(gs.player.location)
    if not room:
        return None
    norm_target = _normalize(target)
    for direction, dest_id in room.exits.items():
        norm_dir = _normalize(direction)
        # examine_desk should match desk, examine desk, or examine_desk.
        stripped = norm_dir
        for prefix in ("examine", "inspect", "read", "open", "use"):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix):]
                break
        if norm_target and (norm_target == stripped or norm_target == norm_dir or stripped in norm_target):
            if dest_id in gs.rooms:
                gs.player.location = dest_id
                was_visited = gs.rooms[dest_id].visited
                gs.rooms[dest_id].visited = True
                return ExecutionResult(
                    success=True,
                    state_changes={"location": dest_id, "was_visited": was_visited},
                    narrative_hint=f"room:{dest_id}:{'visited' if was_visited else 'new'}",
                )
    return None


def _answer_location_question(action: InterpretedAction, gs: GameState) -> ExecutionResult | None:
    target = (action.target or "").strip().lower()
    if not target:
        return None
    room = gs.rooms.get(gs.player.location)
    if not room:
        return None

    # Match requested location by room id or room name.
    wanted = _normalize(target)
    dest_id = None
    for rid, candidate in gs.rooms.items():
        if wanted in _normalize(rid) or wanted in _normalize(candidate.name):
            dest_id = rid
            break
    if not dest_id:
        return None

    # Direct exit from current room?
    for direction, rid in room.exits.items():
        if rid == dest_id:
            dest_name = gs.rooms[dest_id].name
            return ExecutionResult(True, narrative_hint=f"location:{dest_name} is {direction} from here.")

    # Find a short path with BFS.
    from collections import deque
    queue = deque([(gs.player.location, [])])
    seen = {gs.player.location}
    while queue:
        rid, path = queue.popleft()
        if rid == dest_id:
            if not path:
                return ExecutionResult(True, narrative_hint=f"location:You are already in {gs.rooms[dest_id].name}.")
            steps = _route_steps_text(path)
            return ExecutionResult(True, narrative_hint=f"location:To reach {gs.rooms[dest_id].name}, {steps}.")
        r = gs.rooms.get(rid)
        if not r:
            continue
        for direction, nxt in r.exits.items():
            if nxt not in seen and nxt in gs.rooms:
                seen.add(nxt)
                queue.append((nxt, path + [direction]))
    return ExecutionResult(True, narrative_hint=f"location:You know of {gs.rooms[dest_id].name}, but you do not know a route from here yet.")


# ─── Lookup helpers ───────────────────────────────────────────────────────────

def _find_object(target: str, gs: GameState) -> "GameObject | None":
    """Find an object in current room by name or id, allowing spaces/underscores."""
    room = gs.rooms.get(gs.player.location)
    candidates = (room.objects if room else []) + gs.player.inventory
    target_norm = _normalize(target)
    for oid in candidates:
        obj = gs.objects.get(oid)
        if not obj:
            continue
        id_norm = _normalize(obj.id)
        name_norm = _normalize(obj.name)
        if target_norm and (target_norm in name_norm or target_norm in id_norm or name_norm in target_norm):
            return obj
    return None


def _find_object_in_inventory(target: str, gs: GameState) -> "GameObject | None":
    target_norm = _normalize(target)
    for oid in gs.player.inventory:
        obj = gs.objects.get(oid)
        if not obj:
            continue
        if target_norm and (target_norm in _normalize(obj.name) or target_norm in _normalize(obj.id)):
            return obj
    return None


def _find_npc(target: str, gs: GameState) -> "NPC | None":
    """Find an NPC in current room by name or id, allowing spaces/underscores."""
    room = gs.rooms.get(gs.player.location)
    target_norm = _normalize(target)

    def matches(npc) -> bool:
        name_norm = _normalize(npc.name)
        id_norm = _normalize(npc.id)
        first = _normalize(npc.name.split()[0]) if npc.name.split() else ""
        last = _normalize(npc.name.split()[-1]) if npc.name.split() else ""
        return bool(target_norm and (
            target_norm in name_norm or target_norm in id_norm or
            name_norm in target_norm or target_norm in {first, last}
        ))

    candidates = room.npcs if room else []
    for nid in candidates:
        npc = gs.npcs.get(nid)
        if npc and matches(npc):
            return npc
    # Also search all NPCs if not found in room (for accuse only / broad references).
    for npc in gs.npcs.values():
        if matches(npc):
            return npc
    return None


def _unlock_dependent_clues(clue_id: str, gs: GameState) -> None:
    """Move hidden objects into their rooms when their prerequisite clue is found."""
    for obj in gs.objects.values():
        if obj.location.startswith("hidden_") and obj.clue_id:
            for clue in gs.crime_state.get("clues", []):
                if clue["id"] == obj.clue_id and clue.get("prerequisite_clue_id") == clue_id:
                    room_part = obj.location.replace("hidden_", "")
                    obj.location = room_part
                    room = gs.rooms.get(room_part)
                    if room and obj.id not in room.objects:
                        room.objects.append(obj.id)
