"""
world/game_state.py — Core game world state data structures.

This is the global state the game engine maintains throughout a playthrough.
It tracks:
  - Rooms and their connections (the location graph)
  - Objects in each room and their state
  - NPCs and their state (interviewed, suspicious, cleared, etc.)
  - The player's location and inventory
  - Which plot points / clues have been executed / discovered
  - The causal link plan (for Template 2 accommodation)
  - Drama manager state (stuck counter, denied plot points, etc.)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ─── Enums ────────────────────────────────────────────────────────────────────

class ActionCategory(Enum):
    CONSTITUENT  = "constituent"   # advances a plot point
    CONSISTENT   = "consistent"    # fine, doesn't break anything
    EXCEPTIONAL  = "exceptional"   # breaks a causal link


class ClueStatus(Enum):
    HIDDEN      = "hidden"       # player doesn't know it exists
    ACCESSIBLE  = "accessible"   # player can find it now
    DISCOVERED  = "discovered"   # player has found it


class NPCStatus(Enum):
    NOT_MET        = "not_met"
    MET            = "met"
    INTERVIEWED    = "interviewed"
    SUSPICIOUS     = "suspicious"
    CLEARED        = "cleared"


class PlotPointStatus(Enum):
    LOCKED    = "locked"      # prerequisites not met
    AVAILABLE = "available"   # ready to be executed
    DONE      = "done"        # executed
    DENIED    = "denied"      # DM has blocked it (temporarily or permanently)


# ─── Room ─────────────────────────────────────────────────────────────────────

@dataclass
class Room:
    id: str                              # e.g. "server_room"
    name: str                            # e.g. "Server Room"
    description: str                     # atmospheric description
    exits: dict[str, str]                # direction -> room_id
    objects: list[str]                   # object ids present here
    npcs: list[str]                      # npc ids present here
    visited: bool = False

    def describe(self) -> str:
        exit_str = ", ".join(
            f"{d} → {r}" for d, r in self.exits.items()
        ) or "none"
        obj_str  = ", ".join(self.objects) if self.objects else "nothing of note"
        npc_str  = ", ".join(self.npcs)    if self.npcs    else "no one"
        visited  = "" if not self.visited else " (you've been here before)"
        return (
            f"**{self.name}**{visited}\n"
            f"{self.description}\n"
            f"Exits: {exit_str}\n"
            f"Objects here: {obj_str}\n"
            f"People here: {npc_str}"
        )


# ─── Object ───────────────────────────────────────────────────────────────────

@dataclass
class GameObject:
    id: str
    name: str
    description: str
    location: str            # room_id or "inventory" or "hidden"
    state: dict[str, Any] = field(default_factory=dict)
    # e.g. {"examined": False, "taken": False, "damaged": False}
    clue_id: str | None = None   # links to crime state clue if relevant
    is_evidence: bool = False


# ─── NPC ──────────────────────────────────────────────────────────────────────

@dataclass
class NPC:
    id: str
    name: str
    occupation: str
    location: str            # room_id
    status: NPCStatus = NPCStatus.NOT_MET
    personality: str = ""
    alibi: str = ""
    known_facts: list[str] = field(default_factory=list)
    # Facts this NPC will reveal when interviewed (unlocked by clue discovery)
    locked_facts: list[tuple[str, str]] = field(default_factory=list)
    # list of (required_clue_id, fact_text) — fact revealed only after clue found
    is_culprit: bool = False
    is_cleared: bool = False


# ─── Causal Link (for Template 2) ─────────────────────────────────────────────

@dataclass
class CausalLink:
    """
    Represents a dependency between two plot points.
    condition must remain TRUE from after `from_plot` until `to_plot` executes.
    """
    id: str
    from_plot: str           # plot point id that establishes the condition
    to_plot: str             # plot point id that consumes/requires the condition
    condition: str           # natural language description of what must be true
    condition_key: str       # state key to check (e.g. "clue_01_accessible")
    active: bool = True      # False once to_plot is executed or condition broken


# ─── Plot Point ───────────────────────────────────────────────────────────────

@dataclass
class PlotPoint:
    id: str
    description: str          # what happens / what the player needs to do
    prerequisites: list[str]  # plot point ids that must be DONE first
    status: PlotPointStatus = PlotPointStatus.LOCKED
    location_hint: str = ""   # which room this tends to happen in
    # What state changes when this plot point executes
    effects: dict[str, Any] = field(default_factory=dict)
    # e.g. {"clue_03_status": "accessible", "npc_reed_status": "suspicious"}


# ─── Player ───────────────────────────────────────────────────────────────────

@dataclass
class Player:
    location: str                        # current room_id
    inventory: list[str] = field(default_factory=list)   # object ids
    discovered_clues: list[str] = field(default_factory=list)
    interviewed_npcs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)       # player's notebook
    accusation_made: bool = False
    accusation_target: str | None = None


# ─── Master Game State ────────────────────────────────────────────────────────

@dataclass
class GameState:
    # Core world
    rooms: dict[str, Room]
    objects: dict[str, GameObject]
    npcs: dict[str, NPC]
    player: Player

    # Story structure
    plot_points: dict[str, PlotPoint]
    causal_links: list[CausalLink]
    crime_state: dict[str, Any]         # original Phase 1 JSON

    # Progress tracking
    executed_plot_points: list[str] = field(default_factory=list)
    broken_causal_links: list[str] = field(default_factory=list)
    turn_count: int = 0
    game_over: bool = False
    game_won: bool = False

    # Drama manager state
    consecutive_non_constituent: int = 0  # for hint triggering
    denied_plot_points: dict[str, int] = field(default_factory=dict)
    # denied_plot_points: {plot_id: turns_remaining} (0 = permanent)
    active_hints: list[str] = field(default_factory=list)
    accommodations_made: list[str] = field(default_factory=list)

    # History log
    action_log: list[dict] = field(default_factory=list)

    def get_clue_status(self, clue_id: str) -> ClueStatus:
        obj = next(
            (o for o in self.objects.values() if o.clue_id == clue_id),
            None
        )
        if obj is None:
            return ClueStatus.HIDDEN
        if clue_id in self.player.discovered_clues:
            return ClueStatus.DISCOVERED
        if obj.location == self.player.location or obj.location == "inventory":
            return ClueStatus.ACCESSIBLE
        return ClueStatus.HIDDEN

    def get_available_plot_points(self) -> list[PlotPoint]:
        """Return plot points whose prerequisites are all DONE."""
        available = []
        for pp in self.plot_points.values():
            if pp.status == PlotPointStatus.DONE:
                continue
            if pp.status == PlotPointStatus.DENIED:
                continue
            prereqs_met = all(
                self.plot_points.get(prereq, PlotPoint("", "", [])).status
                == PlotPointStatus.DONE
                for prereq in pp.prerequisites
            )
            if prereqs_met:
                pp.status = PlotPointStatus.AVAILABLE
                available.append(pp)
        return available

    def mark_plot_point_done(self, plot_id: str) -> None:
        if plot_id in self.plot_points:
            self.plot_points[plot_id].status = PlotPointStatus.DONE
            if plot_id not in self.executed_plot_points:
                self.executed_plot_points.append(plot_id)
            # Deactivate causal links whose to_plot is now done
            for link in self.causal_links:
                if link.to_plot == plot_id:
                    link.active = False

    def is_solvable(self) -> bool:
        """Return False if the crime can no longer be solved (game-breaking exception)."""
        # Check that the culprit-reveal plot point is still reachable
        culprit_pp = self.plot_points.get("reveal_culprit")
        if culprit_pp and culprit_pp.status == PlotPointStatus.DENIED:
            return False
        # Check that at least MIN_CLUES_TO_ACCUSE clues are still discoverable
        from config import MIN_CLUES_TO_ACCUSE
        discoverable = sum(
            1 for o in self.objects.values()
            if o.is_evidence and o.location != "destroyed"
        )
        return discoverable >= MIN_CLUES_TO_ACCUSE

    def summary(self) -> str:
        clues_found = len(self.player.discovered_clues)
        total_clues = sum(1 for o in self.objects.values() if o.is_evidence)
        npcs_interviewed = len(self.player.interviewed_npcs)
        total_npcs = len(self.npcs)
        pp_done = len(self.executed_plot_points)
        total_pp = len(self.plot_points)
        return (
            f"Turn {self.turn_count} | "
            f"Clues: {clues_found}/{total_clues} | "
            f"Interviews: {npcs_interviewed}/{total_npcs} | "
            f"Plot points: {pp_done}/{total_pp} | "
            f"Location: {self.rooms.get(self.player.location, Room('?','?','',{},[], [])).name}"
        )
