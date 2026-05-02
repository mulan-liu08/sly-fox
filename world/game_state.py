from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionCategory(Enum):
    CONSTITUENT  = "constituent"   
    CONSISTENT   = "consistent"    
    EXCEPTIONAL  = "exceptional"   


class ClueStatus(Enum):
    HIDDEN      = "hidden"      
    ACCESSIBLE  = "accessible" 
    DISCOVERED  = "discovered"   

class NPCStatus(Enum):
    NOT_MET        = "not_met"
    MET            = "met"
    INTERVIEWED    = "interviewed"
    SUSPICIOUS     = "suspicious"
    CLEARED        = "cleared"


class PlotPointStatus(Enum):
    LOCKED    = "locked"     
    AVAILABLE = "available"   
    DONE      = "done"      
    DENIED    = "denied"      


@dataclass
class Room:
    id: str           
    name: str                    
    description: str                    
    exits: dict[str, str]               
    objects: list[str]                   
    npcs: list[str]                     
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


@dataclass
class GameObject:
    id: str
    name: str
    description: str
    location: str           
    state: dict[str, Any] = field(default_factory=dict)
    clue_id: str | None = None  
    is_evidence: bool = False


@dataclass
class NPC:
    id: str
    name: str
    occupation: str
    location: str          
    status: NPCStatus = NPCStatus.NOT_MET
    personality: str = ""
    alibi: str = ""
    known_facts: list[str] = field(default_factory=list)
    locked_facts: list[tuple[str, str]] = field(default_factory=list)
    is_culprit: bool = False
    is_cleared: bool = False

@dataclass
class CausalLink:
    id: str
    from_plot: str         
    to_plot: str            
    condition: str         
    condition_key: str    
    active: bool = True     


@dataclass
class PlotPoint:
    id: str
    description: str         
    prerequisites: list[str]  
    status: PlotPointStatus = PlotPointStatus.LOCKED
    location_hint: str = ""   
    effects: dict[str, Any] = field(default_factory=dict)


@dataclass
class Player:
    location: str                    
    inventory: list[str] = field(default_factory=list)  
    discovered_clues: list[str] = field(default_factory=list)
    interviewed_npcs: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  
    accusation_made: bool = False
    accusation_target: str | None = None


@dataclass
class GameState:
    rooms: dict[str, Room]
    objects: dict[str, GameObject]
    npcs: dict[str, NPC]
    player: Player

    plot_points: dict[str, PlotPoint]
    causal_links: list[CausalLink]
    crime_state: dict[str, Any]       

    executed_plot_points: list[str] = field(default_factory=list)
    broken_causal_links: list[str] = field(default_factory=list)
    turn_count: int = 0
    game_over: bool = False
    game_won: bool = False

    consecutive_non_constituent: int = 0 
    denied_plot_points: dict[str, int] = field(default_factory=dict)
    active_hints: list[str] = field(default_factory=list)
    accommodations_made: list[str] = field(default_factory=list)

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
            for link in self.causal_links:
                if link.to_plot == plot_id:
                    link.active = False

    def is_solvable(self) -> bool:
        culprit_pp = self.plot_points.get("reveal_culprit")
        if culprit_pp and culprit_pp.status == PlotPointStatus.DENIED:
            return False
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
