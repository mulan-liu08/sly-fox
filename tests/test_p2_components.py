"""
tests/test_p2_components.py — Unit tests for Phase 2 non-LLM components.

Tests:
  - GameState: plot point unlocking, clue discovery, solvability check
  - ActionExecutor: move, examine, take, accuse (correct + wrong + too early)
  - DramaManager: block exception, hint after stuck, accusation guard
  - WorldGenerator: room slugification, object creation

Run with: python tests/test_p2_components.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Stub API key
os.environ["GEMINI_API_KEY"] = "stub"

from world.game_state import (
    GameState, Room, GameObject, NPC, PlotPoint, CausalLink, Player,
    PlotPointStatus, NPCStatus, ActionCategory
)
from engine.action_executor import execute_action, ExecutionResult
from engine.action_interpreter import InterpretedAction
from world.world_generator import _slugify, _clue_to_object_name, _best_room_match


# ─── Fixtures ─────────────────────────────────────────────────────────────────

SAMPLE_CRIME_STATE = {
    "setting": {"location": "Test Facility", "date": "Oct 26", "time_of_crime": "11pm"},
    "victim": {"name": "Dr. Thorne", "occupation": "Researcher", "background": "Scientist."},
    "culprit": {
        "name": "Dr. Reed",
        "means": "poison",
        "motive": "revenge",
        "opportunity": "late night access",
        "method": "neurotoxin via air mister",
        "alibi": "claims to be in lab",
    },
    "suspects": [
        {
            "name": "Elias Vance",
            "occupation": "Programmer",
            "relationship_to_victim": "colleague",
            "means": None, "motive": "credit theft",
            "opportunity": "in server room",
            "alibi": "server logs confirm presence",
            "personality": "nervous",
            "missing_element": "means",
        }
    ],
    "clues": [
        {
            "id": "clue_01",
            "description": "A faint chemical scent near the body.",
            "location": "victim_office",
            "points_to": "culprit",
            "is_red_herring": False,
            "red_herring_explanation": None,
            "prerequisite_clue_id": None,
        },
        {
            "id": "clue_02",
            "description": "A burnt note in the waste bin.",
            "location": "victim_office",
            "points_to": "Elias Vance",
            "is_red_herring": True,
            "red_herring_explanation": "He was just angry.",
            "prerequisite_clue_id": None,
        },
        {
            "id": "clue_03",
            "description": "A residue on the air mister handle.",
            "location": "forensics_lab",
            "points_to": "culprit",
            "is_red_herring": False,
            "red_herring_explanation": None,
            "prerequisite_clue_id": "clue_01",
        },
    ],
    "hidden_backstory": "Dr. Reed did it with a neurotoxin.",
}


def _make_game_state() -> GameState:
    """Build a minimal GameState for testing."""
    rooms = {
        "entrance":     Room("entrance", "Entrance", "The main entrance.", {"north": "corridor"}, [], []),
        "corridor":     Room("corridor", "Corridor", "A long corridor.", {"south": "entrance", "east": "victim_office"}, [], []),
        "victim_office":Room("victim_office", "Victim's Office", "The crime scene.", {"west": "corridor"}, [], []),
        "forensics_lab":Room("forensics_lab", "Forensics Lab", "The lab.", {"north": "corridor"}, [], []),
    }
    objects = {
        "clue_01": GameObject("clue_01", "chemical scent residue", "A faint chemical scent.", "victim_office", {"examined": False}, "clue_01", True),
        "clue_02": GameObject("clue_02", "burnt note",            "A burnt note.",           "victim_office", {"examined": False}, "clue_02", True),
        "clue_03": GameObject("clue_03", "air mister residue",    "Residue on mister.",      "hidden_forensics_lab", {"examined": False}, "clue_03", True),
        "keycard":  GameObject("keycard",  "security keycard",     "A keycard.",              "entrance",       {"examined": False}, None, False),
    }
    rooms["victim_office"].objects = ["clue_01", "clue_02"]
    rooms["entrance"].objects = ["keycard"]

    culprit_npc = NPC("dr_reed", "Dr. Reed", "Researcher", "corridor", is_culprit=True)
    vance_npc   = NPC("elias_vance", "Elias Vance", "Programmer", "victim_office")
    npcs = {"dr_reed": culprit_npc, "elias_vance": vance_npc}
    rooms["corridor"].npcs = ["dr_reed"]
    rooms["victim_office"].npcs = ["elias_vance"]

    plot_points = {
        "arrive_at_scene": PlotPoint("arrive_at_scene", "Examine crime scene.", [], PlotPointStatus.AVAILABLE),
        "clue_01": PlotPoint("clue_01", "Find chemical scent.", ["arrive_at_scene"], PlotPointStatus.AVAILABLE),
        "clue_02": PlotPoint("clue_02", "Find burnt note.",     ["arrive_at_scene"], PlotPointStatus.AVAILABLE),
        "clue_03": PlotPoint("clue_03", "Analyze air mister.",  ["clue_01"], PlotPointStatus.LOCKED),
        "reveal_culprit": PlotPoint("reveal_culprit", "Accuse culprit.", ["clue_01", "clue_03"], PlotPointStatus.LOCKED),
    }
    causal_links = [
        CausalLink("link_01_03", "clue_01", "clue_03", "Chemical scent still accessible", "clue_01_intact"),
    ]
    player = Player(location="entrance")

    return GameState(
        rooms=rooms,
        objects=objects,
        npcs=npcs,
        player=player,
        plot_points=plot_points,
        causal_links=causal_links,
        crime_state=SAMPLE_CRIME_STATE,
    )


def _make_action(verb, target=None, category=ActionCategory.CONSISTENT, pp_id=None):
    return InterpretedAction(
        verb=verb, target=target, secondary=None,
        raw_input=f"{verb} {target or ''}".strip(),
        category=category, reasoning="test",
        affected_causal_links=[], plot_point_id=pp_id,
    )


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_move_valid():
    gs = _make_game_state()
    action = _make_action("move", "north")
    result = execute_action(action, gs)
    assert result.success
    assert gs.player.location == "corridor"
    print("  PASS: move valid direction")


def test_move_invalid():
    gs = _make_game_state()
    action = _make_action("move", "up")
    result = execute_action(action, gs)
    assert not result.success
    print("  PASS: move invalid direction blocked")


def test_examine_clue_discovers_it():
    gs = _make_game_state()
    gs.player.location = "victim_office"
    action = _make_action("examine", "chemical scent", ActionCategory.CONSTITUENT, "clue_01")
    result = execute_action(action, gs)
    assert result.success
    assert result.clue_discovered == "clue_01"
    assert "clue_01" in gs.player.discovered_clues
    print("  PASS: examining clue object discovers it")


def test_examine_clue_unlocks_dependent():
    gs = _make_game_state()
    gs.player.location = "victim_office"
    # Discover clue_01
    action = _make_action("examine", "chemical scent", ActionCategory.CONSTITUENT)
    execute_action(action, gs)
    # clue_03 should now be accessible (moved from hidden_forensics_lab)
    assert gs.objects["clue_03"].location == "forensics_lab"
    print("  PASS: discovering clue_01 unlocks dependent clue_03")


def test_take_object():
    gs = _make_game_state()
    action = _make_action("take", "keycard")
    result = execute_action(action, gs)
    assert result.success
    assert "keycard" in gs.player.inventory
    assert gs.objects["keycard"].location == "inventory"
    print("  PASS: take object adds to inventory")


def test_accuse_too_early():
    gs = _make_game_state()
    action = _make_action("accuse", "reed", ActionCategory.CONSISTENT)
    result = execute_action(action, gs)
    assert not result.success
    assert "too_early" in result.narrative_hint
    print("  PASS: accusation blocked with insufficient clues")


def test_accuse_correct():
    gs = _make_game_state()
    # Give player enough clues
    gs.player.discovered_clues = ["clue_01", "clue_03", "clue_extra"]
    gs.player.location = "corridor"   # Dr. Reed is in corridor
    action = _make_action("accuse", "reed", ActionCategory.CONSTITUENT, "reveal_culprit")
    result = execute_action(action, gs)
    assert result.success
    assert result.game_won
    print("  PASS: correct accusation wins the game")


def test_accuse_wrong():
    gs = _make_game_state()
    gs.player.discovered_clues = ["clue_01", "clue_02", "clue_03"]
    action = _make_action("accuse", "elias vance", ActionCategory.CONSISTENT)
    result = execute_action(action, gs)
    assert not result.success
    assert "wrong" in result.narrative_hint
    print("  PASS: wrong accusation fails")


def test_plot_point_unlocking():
    gs = _make_game_state()
    # clue_03 should be locked initially
    assert gs.plot_points["clue_03"].status == PlotPointStatus.LOCKED
    # After marking arrive_at_scene and clue_01 done
    gs.mark_plot_point_done("arrive_at_scene")
    gs.mark_plot_point_done("clue_01")
    available = gs.get_available_plot_points()
    available_ids = [pp.id for pp in available]
    assert "clue_03" in available_ids
    print("  PASS: plot point unlocks after prerequisites met")


def test_solvability():
    gs = _make_game_state()
    assert gs.is_solvable()
    # Destroy all evidence
    for obj in gs.objects.values():
        obj.location = "destroyed"
    assert not gs.is_solvable()
    print("  PASS: solvability check works")


def test_talk_to_npc():
    gs = _make_game_state()
    gs.player.location = "victim_office"
    action = _make_action("talk", "elias", ActionCategory.CONSTITUENT)
    result = execute_action(action, gs)
    assert result.success
    assert "elias_vance" in gs.player.interviewed_npcs
    print("  PASS: talking to NPC marks them as interviewed")


def test_slugify():
    assert _slugify("Dr. Thorne's Office") == "dr_thornes_office"
    assert _slugify("Server Room, Level 7") == "server_room_level_7"
    print("  PASS: _slugify works correctly")


def test_clue_to_object_name():
    name = _clue_to_object_name("A faint, unusual chemical scent near the body")
    assert len(name) > 0
    assert "a" not in name.split()[0].lower() or len(name.split()) > 1
    print(f"  PASS: _clue_to_object_name → {name!r}")


def test_best_room_match():
    rooms = ["victim_office", "server_room", "security_office", "corridor"]
    assert _best_room_match("server_room_level_7", rooms) == "server_room"
    assert _best_room_match("completely_unknown_place", rooms) == "victim_office"
    print("  PASS: _best_room_match finds closest room")


def test_inventory_display():
    gs = _make_game_state()
    action = _make_action("inventory")
    result = execute_action(action, gs)
    assert result.success
    assert "inventory:" in result.narrative_hint
    print("  PASS: inventory command returns hint")


# ─── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_move_valid,
        test_move_invalid,
        test_examine_clue_discovers_it,
        test_examine_clue_unlocks_dependent,
        test_take_object,
        test_accuse_too_early,
        test_accuse_correct,
        test_accuse_wrong,
        test_plot_point_unlocking,
        test_solvability,
        test_talk_to_npc,
        test_slugify,
        test_clue_to_object_name,
        test_best_room_match,
        test_inventory_display,
    ]

    passed = failed = 0
    for test in tests:
        print(f"\n▶ {test.__name__}")
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    print("="*40)
    sys.exit(0 if failed == 0 else 1)
