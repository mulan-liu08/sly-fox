"""
tests/test_components.py — Unit tests for non-LLM components.

Run with:  python -m pytest tests/ -v
or:        python tests/test_components.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from validators import validate_crime_world_state, summarise_crime_state
from consistency_checker import ConsistencyChecker, SecretTracker, EventMemoryBuffer


# ─── Shared fixture ───────────────────────────────────────────────────────────

SAMPLE_STATE = {
    "setting": {
        "location": "Hargrove Manor, Derbyshire",
        "date": "October 14, 1987",
        "time_of_crime": "11:42 PM"
    },
    "victim": {
        "name": "Reginald Hargrove",
        "occupation": "Industrialist",
        "background": "Ruthless businessman who threatened to disinherit his family."
    },
    "culprit": {
        "name": "Diana Hargrove",
        "means": "Access to prescription potassium chloride from her hospital job",
        "motive": "Stood to inherit £2M only if Reginald died before changing his will",
        "opportunity": "Was alone with Reginald serving his nightly brandy",
        "method": "Dissolved potassium chloride in his brandy, inducing cardiac arrest",
        "alibi": "Claims she was in her room reading from 10 PM onward"
    },
    "suspects": [
        {
            "name": "Victor Hargrove",
            "occupation": "Failed art dealer",
            "relationship_to_victim": "Son",
            "means": "Has access to a hunting rifle but not poison",
            "motive": None,
            "opportunity": "Was at the manor that night",
            "alibi": "Playing cards with the groundskeeper until midnight, verified",
            "personality": "Defensive, quick-tempered, deflects with bravado",
            "missing_element": "motive"
        },
        {
            "name": "Constance Webb",
            "occupation": "Reginald's personal secretary",
            "relationship_to_victim": "Employee / secret confidante",
            "means": None,
            "motive": "Feared being fired after Reginald found a financial discrepancy",
            "opportunity": "Present at the manor for a late meeting",
            "alibi": "Left at 10 PM, confirmed by gate log and taxi receipt",
            "personality": "Meticulous, anxious, over-explains when nervous",
            "missing_element": "means"
        },
        {
            "name": "Dr. Elliot Marsh",
            "occupation": "Family physician",
            "relationship_to_victim": "Doctor and old friend",
            "means": "Extensive pharmaceutical knowledge",
            "motive": "Reginald threatened to expose an old malpractice incident",
            "opportunity": None,
            "alibi": "Attending a medical conference in Edinburgh, hotel and flight records confirmed",
            "personality": "Calm, clinical, reveals little, chooses words with surgical precision",
            "missing_element": "opportunity"
        },
        {
            "name": "Miles Pendleton",
            "occupation": "Estate groundskeeper",
            "relationship_to_victim": "Long-serving employee",
            "means": None,
            "motive": "Reginald had just fired him via letter that afternoon",
            "opportunity": "On-site all evening",
            "alibi": "Playing cards with Victor Hargrove — corroborated by Victor",
            "personality": "Loyal, stoic, slow to trust, speaks only when asked",
            "missing_element": "means"
        }
    ],
    "clues": [
        {
            "id": "clue_01",
            "description": "An empty brandy decanter with a faint medicinal smell near the fireplace",
            "location": "Reginald's study",
            "points_to": "culprit",
            "is_red_herring": False,
            "red_herring_explanation": None,
            "prerequisite_clue_id": None
        },
        {
            "id": "clue_02",
            "description": "A crumpled letter in the bin threatening to change the will within 48 hours",
            "location": "Reginald's study wastepaper bin",
            "points_to": "Diana Hargrove",
            "is_red_herring": False,
            "red_herring_explanation": None,
            "prerequisite_clue_id": None
        },
        {
            "id": "clue_03",
            "description": "A novel on Diana's nightstand with her bookmark only 10 pages in — far too little reading for 90 minutes",
            "location": "Diana's bedroom",
            "points_to": "culprit",
            "is_red_herring": False,
            "red_herring_explanation": None,
            "prerequisite_clue_id": "clue_06"
        },
        {
            "id": "clue_04",
            "description": "Victor's hunting rifle cleaned very recently despite claiming not to have used it",
            "location": "Gun room",
            "points_to": "Victor Hargrove",
            "is_red_herring": True,
            "red_herring_explanation": "Victor had shot at a fox that afternoon — unrelated to the murder",
            "prerequisite_clue_id": None
        },
        {
            "id": "clue_05",
            "description": "A hospital dispensing record showing Diana signed out potassium chloride the previous week for 'equipment calibration'",
            "location": "Hospital pharmacy records (off-site)",
            "points_to": "culprit",
            "is_red_herring": False,
            "red_herring_explanation": None,
            "prerequisite_clue_id": "clue_01"
        },
        {
            "id": "clue_06",
            "description": "Security camera footage showing Diana leaving her room at 11:30 PM, contradicting her alibi",
            "location": "Manor CCTV archive",
            "points_to": "culprit",
            "is_red_herring": False,
            "red_herring_explanation": None,
            "prerequisite_clue_id": "clue_02"
        },
        {
            "id": "clue_07",
            "description": "A threatening note referencing financial records, found in Constance's car",
            "location": "Constance Webb's vehicle",
            "points_to": "Constance Webb",
            "is_red_herring": True,
            "red_herring_explanation": "The note was about a separate property dispute Constance had with a neighbour, nothing to do with Reginald",
            "prerequisite_clue_id": None
        }
    ],
    "timeline": [
        {"time": "7:00 PM", "event": "Dinner at Hargrove Manor — all suspects present", "known_to_detective": True},
        {"time": "10:00 PM", "event": "Constance Webb leaves via front gate", "known_to_detective": True},
        {"time": "10:15 PM", "event": "Victor and Miles begin card game in the kitchen", "known_to_detective": True},
        {"time": "11:30 PM", "event": "Diana Hargrove leaves her room (CCTV)", "known_to_detective": False},
        {"time": "11:42 PM", "event": "Diana adds potassium chloride to Reginald's brandy in his study", "known_to_detective": False},
        {"time": "11:55 PM", "event": "Reginald suffers cardiac arrest", "known_to_detective": True},
        {"time": "12:03 AM", "event": "Victor discovers Reginald's body", "known_to_detective": True}
    ],
    "hidden_backstory": (
        "Diana Hargrove had known for three days that her father intended to rewrite his will, "
        "cutting her out entirely after discovering she had secretly been selling family heirlooms. "
        "With only 48 hours remaining before the solicitor's appointment, she acted. Using pharmaceutical-grade "
        "potassium chloride obtained under a false pretext from her hospital, she dissolved it in Reginald's "
        "nightly brandy while everyone else was occupied. She then returned to her room and staged the appearance "
        "of an evening spent reading. When Reginald collapsed, she was among the first to feign alarm. "
        "The death was initially ruled a heart attack — Reginald had a history of cardiac issues — "
        "but a sharp-eyed toxicologist flagged elevated potassium levels, prompting an investigation."
    )
}


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_validator_passes_valid_state():
    warnings = validate_crime_world_state(SAMPLE_STATE)
    print(f"  Warnings: {warnings}")
    assert isinstance(warnings, list)
    print("  PASS: validator accepts valid state")


def test_validator_rejects_missing_culprit_element():
    import copy
    bad = copy.deepcopy(SAMPLE_STATE)
    bad["culprit"]["means"] = None
    try:
        validate_crime_world_state(bad)
        print("  FAIL: should have raised ValueError")
        assert False
    except ValueError as exc:
        print(f"  PASS: caught expected error → {exc}")


def test_validator_rejects_too_few_clues():
    import copy
    bad = copy.deepcopy(SAMPLE_STATE)
    bad["clues"] = bad["clues"][:2]
    try:
        validate_crime_world_state(bad)
        print("  FAIL: should have raised ValueError")
        assert False
    except ValueError as exc:
        print(f"  PASS: caught expected error → {exc}")


def test_secret_tracker_culprit_identity():
    tracker = SecretTracker(SAMPLE_STATE, target_plot_points=18)
    # Should not be revealable at step 5
    assert not tracker.can_reveal("culprit_identity", 5)
    # Should be revealable at step 16
    assert tracker.can_reveal("culprit_identity", 16)
    print("  PASS: SecretTracker gates culprit identity correctly")


def test_secret_tracker_murder_method():
    tracker = SecretTracker(SAMPLE_STATE, target_plot_points=18)
    assert not tracker.can_reveal("murder_method", 3)
    assert tracker.can_reveal("murder_method", 11)
    print("  PASS: SecretTracker gates murder method correctly")


def test_event_memory_buffer_anti_repetition():
    buf = EventMemoryBuffer()
    # First WITNESS_REFUSES is fine
    assert not buf.is_repetitive("The witness refused to speak and remained silent")
    buf.record("The witness refused to speak and remained silent")
    assert not buf.is_repetitive("She discovered a key clue in the drawer")
    buf.record("She discovered a key clue in the drawer")
    # Second WITNESS_REFUSES right after is repetitive
    buf.record("The suspect refused to talk and stayed silent throughout")
    assert buf.is_repetitive("Another witness refused to answer any questions")
    print("  PASS: EventMemoryBuffer catches repeated obstacle types")


def test_consistency_checker_blocks_early_culprit_reveal():
    checker = ConsistencyChecker(SAMPLE_STATE, target_plot_points=18)
    culprit_name = SAMPLE_STATE["culprit"]["name"]
    text = f"The detective concluded that {culprit_name} was the murderer."
    result = checker.check(text, step=4)  # Too early
    assert not result.is_valid
    print(f"  PASS: ConsistencyChecker blocked early culprit reveal → {result.reason}")


def test_consistency_checker_allows_late_culprit_reveal():
    checker = ConsistencyChecker(SAMPLE_STATE, target_plot_points=18)
    culprit_name = SAMPLE_STATE["culprit"]["name"]
    text = f"The detective concluded that {culprit_name} was the murderer."
    result = checker.check(text, step=16)  # Late enough
    assert result.is_valid
    print(f"  PASS: ConsistencyChecker allows late culprit reveal → {result.reason}")


def test_summarise_crime_state():
    summary = summarise_crime_state(SAMPLE_STATE)
    assert "Diana Hargrove" in summary
    assert "Reginald Hargrove" in summary
    print(f"  PASS: summarise_crime_state → {summary}")


# ─── Runner ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        test_validator_passes_valid_state,
        test_validator_rejects_missing_culprit_element,
        test_validator_rejects_too_few_clues,
        test_secret_tracker_culprit_identity,
        test_secret_tracker_murder_method,
        test_event_memory_buffer_anti_repetition,
        test_consistency_checker_blocks_early_culprit_reveal,
        test_consistency_checker_allows_late_culprit_reveal,
        test_summarise_crime_state,
    ]

    passed = 0
    failed = 0
    for test in tests:
        print(f"\n▶ {test.__name__}")
        try:
            test()
            passed += 1
        except AssertionError:
            print("  FAIL (assertion)")
            failed += 1
        except Exception as exc:
            print(f"  ERROR: {exc}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    print("="*40)
    sys.exit(0 if failed == 0 else 1)
