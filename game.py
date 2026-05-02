"""
game.py — Main interactive game loop for Phase 2.

Ties together:
  WorldGenerator → GameState
  ActionInterpreter → InterpretedAction
  DramaManager → DMDecision (pre-execution for EXCEPTIONAL)
  ActionExecutor → ExecutionResult
  DramaManager.evaluate() (post-execution for CONSTITUENT/CONSISTENT)
  ResponseGenerator → player-facing text

Usage:
  python game.py                                      # generate a new crime state, then play
  python game.py --theme "mountain observatory"       # generate from a theme, then play
  python game.py --crime-state output/crime_state.json # load an existing Phase 1 state
  python game.py --crime-state output/crime_state.json --debug
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import textwrap
from datetime import datetime

from world.world_generator import build_game_world
from engine.action_interpreter import interpret_action
from engine.action_executor import execute_action
from engine.response_generator import generate_response, describe_room
from drama_manager.drama_manager import DramaManager, DMDecision
from world.game_state import ActionCategory, GameState
from config import OUTPUT_DIR


# ─── CLI ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sly Fox Interactive Mystery — Phase 2")
    p.add_argument(
        "--crime-state", default="",
        help="Path to an existing Phase 1 crime_state_*.json file. If omitted, a new crime state is generated."
    )
    p.add_argument(
        "--theme", default="",
        help="Optional seed theme used when generating a new crime state, e.g. 'locked observatory murder'."
    )
    p.add_argument(
        "--no-save-crime-state", action="store_true",
        help="Do not save generated crime state JSON to output/."
    )
    p.add_argument(
        "--debug", action="store_true",
        help="Show DM log, action classifications, and world state"
    )
    p.add_argument(
        "--save-log", action="store_true",
        help="Save the full game log to output/"
    )
    return p.parse_args()


# ─── Game setup ───────────────────────────────────────────────────────────────

def load_crime_state(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_banner(crime_state: dict) -> None:
    victim  = crime_state.get("victim", {}).get("name", "Unknown")
    setting = crime_state.get("setting", {}).get("location", "Unknown location")
    date    = crime_state.get("setting", {}).get("date", "")
    print()
    print("=" * 64)
    print("  🦊  SLY FOX — INTERACTIVE MYSTERY")
    print(f"  Case: The Murder of {victim}")
    print(f"  Scene: {setting}")
    print(f"  Date: {date}")
    print("=" * 64)
    print()
    print("  You are Detective Morgan Reyes.")
    print("  Type commands to investigate. Type HELP for guidance.")
    print("  Type QUIT to exit.")
    print()


def print_intro(gs: GameState) -> None:
    crime  = gs.crime_state
    victim = crime.get("victim", {})
    setting = crime.get("setting", {})

    intro = (
        f"The call came in at {setting.get('time_of_crime', 'late night')}. "
        f"{victim.get('name', 'The victim')}, "
        f"{victim.get('occupation', 'a researcher')}, "
        f"has been found dead at {setting.get('location', 'the facility')}. "
        f"The cause of death appears to be {_death_description(crime)}. "
        f"\n\nYou arrive at the scene. The place is eerily quiet."
    )
    print(_wrap(intro))
    print()
    # Describe starting room
    room = gs.rooms.get(gs.player.location)
    if room:
        print(_wrap(describe_room(gs)))
    print()


def _death_description(crime: dict) -> str:
    method = crime.get("culprit", {}).get("method", "unknown causes")
    # Give the non-spoiler version
    if "toxin" in method.lower() or "poison" in method.lower():
        return "a sudden medical collapse, though something feels off"
    if "hemorrhage" in method.lower():
        return "what appears to be a sudden collapse"
    return "suspicious circumstances"


# ─── Main game loop ───────────────────────────────────────────────────────────

def run_game(gs: GameState, debug: bool = False) -> list[dict]:
    dm = DramaManager(gs)
    game_log: list[dict] = []

    while not gs.game_over:
        gs.turn_count += 1
        print(f"\n{'─'*40}")
        if debug:
            print(f"  [{gs.summary()}]")
        print()

        # ── Get player input ──────────────────────────────────────────────────
        try:
            raw = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Leaving the investigation.")
            break

        if not raw:
            continue

        if raw.lower() in ("quit", "exit", "q"):
            print("  You step away from the investigation.")
            break

        # Soft word limit warning
        if len(raw.split()) > 10:
            print("  (Keep commands to 10 words or fewer for best results.)")
            raw = " ".join(raw.split()[:10])

        # ── Interpret action ──────────────────────────────────────────────────
        print("  ...", end="\r")
        action = interpret_action(raw, gs)

        if debug:
            print(f"  [ACTION] verb={action.verb!r} target={action.target!r} "
                  f"category={action.category.value} | {action.reasoning}")

        # ── Drama Manager pre-execution (for EXCEPTIONAL) ─────────────────────
        dm_decision = DMDecision(action="allow", message="", log_entry="")
        if action.category == ActionCategory.EXCEPTIONAL:
            dm_decision = dm.evaluate(action)
            if debug:
                print(f"  [DM] {dm_decision.log_entry}")
            if dm_decision.action == "block":
                print()
                print(_wrap(f"  {dm_decision.message}"))
                _log_turn(game_log, gs.turn_count, raw, action, None, dm_decision, dm_decision.message)
                continue

        # ── Execute action ────────────────────────────────────────────────────
        result = execute_action(action, gs)

        # ── Drama Manager post-execution ──────────────────────────────────────
        if action.category != ActionCategory.EXCEPTIONAL:
            dm_decision = dm.evaluate(action, result)

        if debug and dm_decision.action != "allow":
            print(f"  [DM] {dm_decision.log_entry}")

        # ── Generate and print response ───────────────────────────────────────
        response = generate_response(
            action_verb=action.verb,
            action_target=action.target,
            execution=result,
            dm_decision=dm_decision,
            game_state=gs,
        )

        print()
        print(_wrap(response))

        # ── DM hint/cause message ─────────────────────────────────────────────
        if dm_decision.action in ("hint", "cause") and dm_decision.message:
            print()
            print(_wrap(f"  *{dm_decision.message}*"))

        # ── Clue discovery notification ───────────────────────────────────────
        if result.clue_discovered:
            clue = next(
                (c for c in gs.crime_state.get("clues", [])
                 if c["id"] == result.clue_discovered),
                None
            )
            if clue:
                obj = next(
                    (o for o in gs.objects.values()
                     if o.clue_id == result.clue_discovered),
                    None
                )
                evidence_name = obj.name if obj else result.clue_discovered
                print()
                print(f"  📋 EVIDENCE LOGGED: {evidence_name}")
                print(_wrap(clue["description"], indent="     "))
                if _clues_needed(gs) > 0:
                    print(f"     Clues found: {len(gs.player.discovered_clues)} | "
                          f"Need {_clues_needed(gs)} more to make accusation")
                else:
                    print(f"     Clues found: {len(gs.player.discovered_clues)} | Enough evidence to accuse")
                    print(_wrap(_accusation_guidance(gs), indent="     "))

        # ── Win/lose ──────────────────────────────────────────────────────────
        if result.game_won:
            _print_win(gs)
            break

        if not gs.is_solvable():
            _print_lose(gs)
            break

        _log_turn(game_log, gs.turn_count, raw, action, result, dm_decision, response)

    return game_log



def _accusation_guidance(gs: GameState) -> str:
    """Tell the player what accusation is now possible and how to reason about it."""
    try:
        from engine.action_executor import _strongest_suspect
        lead = _strongest_suspect(gs)
    except Exception:
        lead = gs.crime_state.get("culprit", {}).get("name", "the strongest suspect")
    lead_npc = next((n for n in gs.npcs.values() if n.name == lead), None)
    if lead_npc and lead_npc.id not in gs.player.interviewed_npcs:
        return (
            "You have enough evidence to focus on a suspect. "
            "Type CASE or SUSPECTS to review the evidence board. "
            f"Strongest current lead: {lead}. Interview them first: talk to {lead}"
        )
    return (
        "You have enough evidence to make an accusation. "
        "Type CASE or SUSPECTS to review the evidence board. "
        f"Strongest current lead: {lead}. Try: accuse {lead}"
    )

def _clues_needed(gs: GameState) -> int:
    from config import MIN_CLUES_TO_ACCUSE
    return max(0, MIN_CLUES_TO_ACCUSE - len(gs.player.discovered_clues))


def _print_win(gs: GameState) -> None:
    culprit   = gs.crime_state.get("culprit", {})
    backstory = gs.crime_state.get("hidden_backstory", "")
    print()
    print("=" * 64)
    print("  ✅  CASE SOLVED")
    print("=" * 64)
    print(_wrap(
        f"\n  You've done it. {culprit.get('name', 'The killer')} is under arrest.\n"
        f"\n  THE TRUTH:\n  {backstory}"
    ))
    print()
    print(f"  Turns taken: {gs.turn_count}")
    print(f"  Clues found: {len(gs.player.discovered_clues)}")
    intervention_count = len(gs.accommodations_made) + len(getattr(gs, "active_hints", []))
    print(f"  DM interventions: {intervention_count}")


def _print_lose(gs: GameState) -> None:
    print()
    print("=" * 64)
    print("  ❌  INVESTIGATION FAILED")
    print("=" * 64)
    print(_wrap(
        "\n  Critical evidence has been destroyed or a key witness is unreachable.\n"
        "  The case cannot be solved. The killer walks free."
    ))


def _log_turn(
    log: list, turn: int, raw: str, action, result, dm, response: str
) -> None:
    log.append({
        "turn": turn,
        "input": raw,
        "verb": action.verb if action else None,
        "category": action.category.value if action else None,
        "dm_action": dm.action if dm else None,
        "response_preview": response[:80] if response else None,
    })


# ─── Formatting ───────────────────────────────────────────────────────────────

def _wrap(text: str, width: int = 72, indent: str = "  ") -> str:
    lines = text.split("\n")
    wrapped = []
    for line in lines:
        if line.strip():
            wrapped.append(textwrap.fill(line, width=width, initial_indent=indent,
                                         subsequent_indent=indent))
        else:
            wrapped.append("")
    return "\n".join(wrapped)


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    # Load or generate crime state. If --crime-state is omitted, Phase 2 now
    # calls the Phase 1-style generator directly and then builds the game world.
    if args.crime_state:
        if not os.path.exists(args.crime_state):
            print(f"Error: crime state file not found: {args.crime_state}")
            sys.exit(1)
        crime_state = load_crime_state(args.crime_state)
    else:
        try:
            from phase1_generator import generate_crime_state
            crime_state, _state_path = generate_crime_state(
                seed_theme=args.theme,
                save=not args.no_save_crime_state,
            )
        except Exception as exc:
            print(f"Error: failed to generate a crime state: {exc}")
            print("Tip: set GEMINI_API_KEY or pass --crime-state PATH to load an existing state.")
            sys.exit(1)

    print_banner(crime_state)

    # Build game world
    gs = build_game_world(crime_state)

    # Print intro
    print_intro(gs)

    # Run game
    game_log = run_game(gs, debug=args.debug)

    # Save log
    if args.save_log:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(OUTPUT_DIR, f"game_log_{ts}.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "crime_state_summary": {
                    "victim": crime_state.get("victim", {}).get("name"),
                    "culprit": crime_state.get("culprit", {}).get("name"),
                    "setting": crime_state.get("setting", {}).get("location"),
                },
                "turns": game_log,
                "dm_log": gs.drama_log if hasattr(gs, "drama_log") else [],
                "final_state": {
                    "clues_found": gs.player.discovered_clues,
                    "turns": gs.turn_count,
                    "won": gs.game_won,
                    "accommodations": gs.accommodations_made,
                }
            }, f, indent=2)
        print(f"\n  💾  Game log saved → {log_path}")


if __name__ == "__main__":
    main()
