from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import re

from llm_client import call_llm
from config import ACTION_MODEL, ACTION_TEMP
from world.game_state import ActionCategory, GameState



KNOWN_VERBS = {
    "move", "go", "walk", "run",         
    "examine", "look", "inspect", "read", "smell", "touch",  
    "take", "pick_up", "grab",           
    "drop", "put_down",                  
    "talk", "ask", "interview", "question", "accuse", 
    "use", "open", "unlock", "close",    
    "show", "give",                       
    "search", "investigate",              
    "note", "record",                   
    "wait", "rest",                      
    "help", "inventory", "map", "case", "evidence", "clues", "suspects", "hint",
    "destroy", "break", "damage",         
    "kill", "attack",                    
    "hide", "remove", "steal",           
}


@dataclass
class InterpretedAction:
    verb: str                            
    target: str | None                   
    secondary: str | None              
    raw_input: str                      
    category: ActionCategory            
    reasoning: str                      
    affected_causal_links: list[str]    
    plot_point_id: str | None            


def interpret_action(
    raw_input: str,
    game_state: GameState,
) -> InterpretedAction:
    words = raw_input.strip().split()
    if len(words) > 12:
        raw_input = " ".join(words[:12]) + "…"

    simple = _parse_simple_command(raw_input, game_state)
    if simple is not None:
        return simple

    context = _build_context(game_state)
    prompt  = _build_prompt(raw_input, context, game_state)

    try:
        result = call_llm(
            prompt=prompt,
            model_name=ACTION_MODEL,
            expect_json=True,
            temperature=ACTION_TEMP,
            max_output_tokens=512,
        )
        return _parse_llm_result(result, raw_input, game_state)
    except Exception as exc:
        recovered = _fallback_parse(raw_input, f"Could not parse input ({exc}). Treating as consistent.")
        return recovered

def _make_action(
    *,
    verb: str,
    target: str | None,
    raw_input: str,
    reasoning: str = "Parsed by deterministic command parser.",
    category: ActionCategory = ActionCategory.CONSISTENT,
    secondary: str | None = None,
) -> InterpretedAction:
    return InterpretedAction(
        verb=verb,
        target=target,
        secondary=secondary,
        raw_input=raw_input,
        category=category,
        reasoning=reasoning,
        affected_causal_links=[],
        plot_point_id=None,
    )


def _clean_target(text: str) -> str | None:
    text = re.sub(r"^(?:the|a|an)\s+", "", text.strip().lower())
    return text or None


def _normalize_command_text(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _parse_simple_command(raw_input: str, gs: GameState) -> InterpretedAction | None:
    text = raw_input.strip().lower()
    text = re.sub(r"[^a-z0-9_\s'-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return _make_action(verb="unknown", target=None, raw_input=raw_input, reasoning="Empty command.")

    if text in {"help", "h", "commands"}:
        return _make_action(verb="help", target=None, raw_input=raw_input)
    if text in {"hint", "what next", "next", "what should i do", "what do i do", "guide me"}:
        return _make_action(verb="hint", target=None, raw_input=raw_input)
    if text in {"case", "case board", "notebook", "detective notebook", "status", "progress"}:
        return _make_action(verb="case", target=None, raw_input=raw_input)
    if text in {"evidence", "clues", "evidence list", "show evidence", "what clues do i have"}:
        return _make_action(verb="evidence", target=None, raw_input=raw_input)
    if text in {"suspects", "suspect list", "who are the suspects", "who can i accuse", "who should i accuse", "who is suspicious"}:
        return _make_action(verb="suspects", target=None, raw_input=raw_input)
    if text in {"inventory", "inv", "i", "pockets"}:
        return _make_action(verb="inventory", target=None, raw_input=raw_input)
    if text in {"map", "locations"}:
        return _make_action(verb="map", target=None, raw_input=raw_input)
    if text in {"exits", "where can i go", "where can i go?", "where do i go", "where do i go?", "what exits", "show exits", "available exits", "where can i move"}:
        return _make_action(verb="exits", target=None, raw_input=raw_input)

    directions = {
        "n": "north", "s": "south", "e": "east", "w": "west",
        "ne": "northeast", "nw": "northwest", "se": "southeast", "sw": "southwest",
        "u": "up", "d": "down",
        "north": "north", "south": "south", "east": "east", "west": "west",
        "northeast": "northeast", "northwest": "northwest",
        "southeast": "southeast", "southwest": "southwest",
        "up": "up", "down": "down", "inside": "inside", "outside": "outside",
    }
    if text in directions:
        return _make_action(verb="go", target=directions[text], raw_input=raw_input)

    room = gs.rooms.get(gs.player.location)
    if room:
        norm_text = _normalize_command_text(text)
        for direction, room_id in room.exits.items():
            dir_text = direction.lower()
            clean = dir_text.replace("_", " ")
            norm_dir = _normalize_command_text(clean)
            stripped = clean
            for prefix in ("to ", "through ", "into ", "back to ", "examine ", "inspect ", "read ", "open ", "use "):
                if stripped.startswith(prefix):
                    stripped = stripped[len(prefix):]
                    break
            norm_stripped = _normalize_command_text(stripped)
            dest = gs.rooms.get(room_id)
            norm_dest = _normalize_command_text(dest.name) if dest else ""
            if norm_text in {norm_dir, norm_stripped, norm_dest}:
                if clean.startswith(("examine ", "inspect ", "read ", "open ", "use ")):
                    target = clean.split(" ", 1)[1]
                    return _make_action(verb="examine", target=target, raw_input=raw_input)
                return _make_action(verb="go", target=clean, raw_input=raw_input)

    if text in {"look", "look around", "examine room", "inspect room", "where am i", "what is here"}:
        return _make_action(verb="look", target="around", raw_input=raw_input)

    loc_match = re.match(r"^(?:where is|where's|how do i get to|how can i get to|directions to)\s+(.+)$", text)
    if loc_match:
        return _make_action(verb="ask", target=_clean_target(loc_match.group(1)), raw_input=raw_input)

    if re.match(r"^(?:what was|what is|whats|what's).*(?:cause of death|death|killed|murder weapon|method)", text):
        return _make_action(verb="ask", target="cause of death", raw_input=raw_input)
    if re.match(r"^(?:who should i accuse|who do i accuse|who is the killer|who is culprit|who did it)", text):
        return _make_action(verb="case", target="accusation", raw_input=raw_input)

    if re.match(r"^(?:who|is there anyone|anyone|who is|whos|who's).*(?:here|room|around)?$", text):
        return _make_action(verb="look", target="people", raw_input=raw_input)
    if text in {"search", "search room", "search area", "investigate", "investigate room"}:
        return _make_action(verb="search", target="room", raw_input=raw_input)
    if text in {"wait", "rest", "sleep", "take a nap", "nap", "sit down", "pause"}:
        return _make_action(verb="wait", target=None, raw_input=raw_input)

    patterns: list[tuple[str, str]] = [
        (r"^(?:take note of|make note of|note|record)\s+(.+)$", "examine"),
        (r"^(?:pick up|pickup|take|get|grab)\s+(.+)$", "take"),
        (r"^(?:drop|put down|leave)\s+(.+)$", "drop"),
        (r"^(?:go|move|walk|run|enter)\s+(?:to|toward|towards|into|in|inside|through|the)?\s*(.+)$", "go"),
        (r"^(?:look at|examine|inspect|read|smell|touch|notice)\s+(.+)$", "examine"),
        (r"^(?:talk to|speak to|interview|question|ask)\s+(.+)$", "talk"),
        (r"^(?:use|open|unlock|close)\s+(.+)$", "use"),
        (r"^(?:accuse)\s+(.+)$", "accuse"),
        (r"^(?:show|give)\s+(.+?)\s+(?:to)\s+(.+)$", "show"),
        (r"^(?:destroy|break|damage)\s+(.+)$", "destroy"),
        (r"^(?:kill|attack)\s+(.+)$", "attack"),
        (r"^(?:hide|remove|steal)\s+(.+)$", "remove"),
    ]

    for pattern, verb in patterns:
        match = re.match(pattern, text)
        if not match:
            continue
        if verb == "show" and len(match.groups()) >= 2:
            return _make_action(
                verb="show",
                target=_clean_target(match.group(1)),
                secondary=_clean_target(match.group(2)),
                raw_input=raw_input,
            )
        return _make_action(verb=verb, target=_clean_target(match.group(1)), raw_input=raw_input)

    return None


def _fallback_parse(raw_input: str, reasoning: str) -> InterpretedAction:
    text = raw_input.strip().lower()
    words = text.split()
    if words:
        first = words[0]
        if first in {"go", "move", "walk", "run", "enter", "to"}:
            return _make_action(verb="go", target=_clean_target(" ".join(words[1:])), raw_input=raw_input, reasoning=reasoning)
        if first in {"take", "grab", "get"}:
            return _make_action(verb="take", target=_clean_target(" ".join(words[1:])), raw_input=raw_input, reasoning=reasoning)
        if first in {"look", "examine", "inspect", "read"}:
            return _make_action(verb="examine", target=_clean_target(" ".join(words[1:])) or "around", raw_input=raw_input, reasoning=reasoning)

    return _make_action(verb="unknown", target=None, raw_input=raw_input, reasoning=reasoning)

def _build_context(gs: GameState) -> dict[str, Any]:
    room = gs.rooms.get(gs.player.location)
    objects_here = [
        f"{gs.objects[oid].name} (id:{oid})"
        for oid in (room.objects if room else [])
        if oid in gs.objects
    ]
    npcs_here = [
        f"{gs.npcs[nid].name} (id:{nid})"
        for nid in (room.npcs if room else [])
        if nid in gs.npcs
    ]
    inventory = [
        gs.objects[oid].name for oid in gs.player.inventory if oid in gs.objects
    ]
    available_pps = [
        pp.description for pp in gs.get_available_plot_points()
    ]
    active_links = [
        f"{lk.id}: {lk.condition}"
        for lk in gs.causal_links if lk.active
    ]
    clues_found = gs.player.discovered_clues

    return {
        "room": room.name if room else "unknown",
        "objects_here": objects_here,
        "npcs_here": npcs_here,
        "inventory": inventory,
        "available_plot_points": available_pps,
        "active_causal_links": active_links,
        "clues_found": clues_found,
    }


def _build_prompt(raw_input: str, ctx: dict, gs: GameState) -> str:
    culprit_name = gs.crime_state.get("culprit", {}).get("name", "unknown")

    return f"""You are the action interpreter for a murder mystery text game.

CURRENT STATE:
Room: {ctx['room']}
Objects here: {ctx['objects_here']}
People here: {ctx['npcs_here']}
Inventory: {ctx['inventory']}
Clues found so far: {ctx['clues_found']}
Active causal links (must not be broken): {ctx['active_causal_links']}
Available plot points (things that could be advanced): {ctx['available_plot_points']}

PLAYER INPUT: "{raw_input}"

Classify this action and return JSON with these fields:
{{
  "verb": "normalized verb from this list: {sorted(KNOWN_VERBS)}",
  "target": "the main object/person/direction being acted on, or null",
  "secondary": "secondary target if any (e.g. who to show object to), or null",
  "category": "constituent | consistent | exceptional",
  "reasoning": "1 sentence explaining why this category",
  "affected_causal_links": ["list of causal link ids that this action would break, if exceptional"],
  "plot_point_id": "id of the plot point this advances if constituent, else null"
}}

Category definitions:
- constituent: directly advances one of the available plot points listed above
- consistent: does not advance a plot point but also does not break any active causal links
  (e.g. moving around, examining irrelevant objects, asking about unrelated topics)
- exceptional: would destroy evidence, make a witness permanently unavailable, or
  otherwise break an active causal link making the crime unsolvable

IMPORTANT RULES:
- If the player tries to ACCUSE someone and has found fewer than 3 clues, classify as
  consistent (not enough evidence) NOT constituent
- The culprit is {culprit_name} — do NOT reveal this in reasoning
- If truly uncertain between consistent and exceptional, choose consistent (safer)
- Destroying or removing evidence objects = exceptional
- Attacking or killing any NPC = exceptional
- Locking a room that has required clues in it = exceptional

Return ONLY the JSON object, no other text."""


def _parse_llm_result(
    result: dict,
    raw_input: str,
    gs: GameState,
) -> InterpretedAction:
    category_str = result.get("category", "consistent").lower()
    if category_str == "constituent":
        category = ActionCategory.CONSTITUENT
    elif category_str == "exceptional":
        category = ActionCategory.EXCEPTIONAL
    else:
        category = ActionCategory.CONSISTENT

    verb = result.get("verb", "unknown")
    if verb == "accuse":
        from config import MIN_CLUES_TO_ACCUSE
        if len(gs.player.discovered_clues) < MIN_CLUES_TO_ACCUSE:
            category = ActionCategory.CONSISTENT
            result["reasoning"] = (
                f"Player tried to accuse but only has "
                f"{len(gs.player.discovered_clues)}/{MIN_CLUES_TO_ACCUSE} "
                f"required clues. Not enough evidence yet."
            )

    return InterpretedAction(
        verb=verb,
        target=result.get("target"),
        secondary=result.get("secondary"),
        raw_input=raw_input,
        category=category,
        reasoning=result.get("reasoning", ""),
        affected_causal_links=result.get("affected_causal_links", []),
        plot_point_id=result.get("plot_point_id"),
    )
