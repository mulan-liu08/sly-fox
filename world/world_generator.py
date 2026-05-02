from __future__ import annotations
import json
import re
from typing import Any

from llm_client import call_llm
from config import WORLD_MODEL, ACTION_TEMP
from world.game_state import (
    GameState, Room, GameObject, NPC, PlotPoint, CausalLink, Player,
    PlotPointStatus, NPCStatus
)

def build_game_world(crime_state: dict[str, Any]) -> GameState:
    print("Building game world from crime state…")

    print("Extracting locations…", end=" ", flush=True)
    rooms = _generate_rooms(crime_state)
    print(f"({len(rooms)} rooms)")

    print("Creating objects…", end=" ", flush=True)
    objects = _create_objects(crime_state, rooms)
    print(f"({len(objects)} objects)")

    print("    Creating NPCs…", end=" ", flush=True)
    npcs = _create_npcs(crime_state, rooms)
    print(f"({len(npcs)} NPCs)")

    print("    Building plot points…", end=" ", flush=True)
    plot_points = _build_plot_points(crime_state)
    print(f"({len(plot_points)} plot points)")

    causal_links = _build_causal_links(crime_state, plot_points)
    print(f"Causal links: {len(causal_links)}")

    entry_room = _get_entry_room(rooms)
    player = Player(location=entry_room)

    state = GameState(
        rooms=rooms,
        objects=objects,
        npcs=npcs,
        player=player,
        plot_points=plot_points,
        causal_links=causal_links,
        crime_state=crime_state,
    )

    state.mark_plot_point_done("arrive_at_scene")

    state.get_available_plot_points()

    print("Game world ready.")
    return state


def _generate_rooms(crime_state: dict) -> dict[str, Room]:
    setting  = crime_state["setting"]["location"]
    clues    = crime_state.get("clues", [])
    timeline = crime_state.get("timeline", [])

    raw_locations = set()
    raw_locations.add("entrance") 
    raw_locations.add("victim_office")

    for c in clues:
        loc = c.get("location", "")
        if loc:
            raw_locations.add(_slugify(loc))

    standard = ["security_office", "common_area", "corridor"]
    for s in standard:
        raw_locations.add(s)

    prompt = (
        f"You are designing a text adventure game set in: {setting}\n\n"
        "Generate a JSON object with a 'rooms' array. Each room must have:\n"
        "  id: snake_case unique identifier\n"
        "  name: short display name (3-5 words)\n"
        "  description: 2-3 sentence atmospheric description (no puzzle spoilers)\n"
        "  exits: object mapping direction strings to room ids "
        "(use 'north','south','east','west','up','down' or named like 'to_lab')\n\n"
        f"Include AT MINIMUM these locations (use these exact ids):\n"
        + "\n".join(f"  - {loc}" for loc in sorted(raw_locations))
        + "\n\nAlso add 2-3 connecting corridors or transitional spaces that make "
        "commonsense given the setting. Ensure every room is reachable. "
        "Entrance must connect to at least 2 other rooms. "
        "Return ONLY valid JSON, nothing else."
    )

    try:
        data = call_llm(
            prompt=prompt,
            model_name=WORLD_MODEL,
            expect_json=True,
            temperature=0.3,
            max_output_tokens=10000,
        )
        rooms_data = data.get("rooms", [])
    except Exception as e:
        print(f"\n    [world_gen] LLM room generation failed ({e}), using fallback")
        rooms_data = _fallback_rooms(crime_state)

    rooms: dict[str, Room] = {}
    for r in rooms_data:
        room_id = r.get("id", "unknown")
        rooms[room_id] = Room(
            id=room_id,
            name=r.get("name", room_id.replace("_", " ").title()),
            description=r.get("description", "A nondescript room."),
            exits=r.get("exits", {}),
            objects=[],
            npcs=[],
        )

    return rooms


def _fallback_rooms(crime_state: dict) -> list[dict]:
    setting = crime_state["setting"]["location"]
    return [
        {"id": "entrance",       "name": "Main Entrance",    "description": f"The entrance to {setting}.", "exits": {"north": "corridor"}},
        {"id": "corridor",       "name": "Main Corridor",    "description": "A long corridor connecting the facility's wings.", "exits": {"south": "entrance", "east": "victim_office", "west": "security_office", "north": "common_area"}},
        {"id": "victim_office",  "name": "Victim's Office",  "description": "The victim's private workspace, now a crime scene.", "exits": {"west": "corridor"}},
        {"id": "security_office","name": "Security Office",  "description": "The facility's security hub.", "exits": {"east": "corridor"}},
        {"id": "common_area",    "name": "Common Area",      "description": "A shared lounge and meeting space.", "exits": {"south": "corridor"}},
        {"id": "suspect_lab",    "name": "Research Lab",     "description": "A secondary laboratory.", "exits": {"south": "corridor"}},
    ]


def _starter_access_item(crime_state: dict[str, Any]) -> tuple[str, str]:
    setting = crime_state.get("setting", {}) or {}
    location = str(setting.get("location", "")).lower()
    date_text = str(setting.get("date", "")).lower()
    victim = crime_state.get("victim", {}) or {}
    victim_text = " ".join(str(v) for v in victim.values()).lower()
    corpus = " ".join([location, date_text, victim_text])

    year_match = re.search(r"\b(1[6-9]\d{2}|20\d{2})\b", date_text)
    year = int(year_match.group(1)) if year_match else None
    historical = year is not None and year < 1970

    if historical or any(word in corpus for word in (
        "manor", "mansion", "estate", "castle", "abbey", "chateau",
        "highlands", "victorian", "edwardian", "192", "193", "194",
    )):
        return (
            "brass house key",
            "A heavy brass key issued by the household staff. It may open service doors or private passages nearby.",
        )

    if any(word in corpus for word in ("hotel", "resort", "casino", "cruise", "ship", "train")):
        return (
            "guest access pass",
            "A guest access pass left near the entrance. It may help you move through restricted areas.",
        )

    if any(word in corpus for word in (
        "observatory", "laboratory", "lab", "facility", "research", "campus",
        "station", "corporate", "office", "security",
    )):
        return (
            "access pass",
            "A simple access pass left near the entrance. It may help you move through secured parts of the site.",
        )

    return (
        "entry key",
        "A small key or access token left near the entrance. It may help you move deeper into the scene.",
    )

def _create_objects(crime_state: dict, rooms: dict) -> dict[str, GameObject]:
    objects: dict[str, GameObject] = {}
    clues = crime_state.get("clues", [])
    room_ids = list(rooms.keys())

    for clue in clues:
        obj_id   = clue["id"]
        raw_loc  = _slugify(clue.get("location", "victim_office"))
        room_id  = raw_loc if raw_loc in rooms else _best_room_match(raw_loc, room_ids)

        obj = GameObject(
            id=obj_id,
            name=_clue_to_object_name(clue["description"]),
            description=clue["description"],
            location=room_id,
            state={"examined": False, "taken": False},
            clue_id=clue["id"],
            is_evidence=True,
        )
        objects[obj_id] = obj

        if room_id in rooms:
            if obj_id not in rooms[room_id].objects:
                rooms[room_id].objects.append(obj_id)

        if clue.get("prerequisite_clue_id"):
            obj.location = "hidden_" + room_id
            if obj_id in rooms.get(room_id, Room("","","",{},[],"")).objects:
                rooms[room_id].objects.remove(obj_id)

    access_name, access_desc = _starter_access_item(crime_state)
    flavor = [
        GameObject(id="notebook", name="case notebook",
                   description="Your pocket notebook for recording observations and suspect statements.",
                   location="inventory", state={"examined": False, "taken": True}),
        GameObject(id="coffee_mug", name="cold drink cup",
                   description="An abandoned cup, long cold. Someone was here recently.",
                   location="victim_office", state={"examined": False}),
        GameObject(id="access_item", name=access_name,
                   description=access_desc,
                   location="entrance", state={"examined": False, "taken": False}),
    ]
    for fobj in flavor:
        objects[fobj.id] = fobj
        room_id = fobj.location
        if room_id in rooms and fobj.id not in rooms[room_id].objects:
            rooms[room_id].objects.append(fobj.id)

    return objects

def _create_npcs(crime_state: dict, rooms: dict) -> dict[str, NPC]:
    npcs: dict[str, NPC] = {}
    room_ids = list(rooms.keys())

    all_chars = crime_state.get("suspects", []) + [
        {**crime_state["culprit"],
         "name": crime_state["culprit"]["name"],
         "occupation": "Researcher",
         "alibi": crime_state["culprit"]["alibi"],
         "personality": "Cool and composed, deflects with technical detail.",
         "_is_culprit": True}
    ]

    npc_rooms = ["security_office", "common_area", "suspect_lab", "corridor", "victim_office"]
    for i, char in enumerate(all_chars):
        npc_id   = _slugify(char["name"])
        is_culprit = char.get("_is_culprit", False) or \
                     char["name"] == crime_state["culprit"]["name"]

        if is_culprit:
            room_id = "suspect_lab" if "suspect_lab" in rooms else "corridor"
        else:
            room_id = npc_rooms[i % len(npc_rooms)]
            if room_id not in rooms:
                room_id = room_ids[i % len(room_ids)]

        locked_facts = []
        for clue in crime_state.get("clues", []):
            if clue.get("points_to") == char["name"]:
                locked_facts.append((
                    clue["id"],
                    f"When shown evidence, {char['name']} reluctantly admits: "
                    f"{clue['description']}"
                ))

        known_facts = []
        relationship = char.get("relationship_to_victim")
        if relationship:
            known_facts.append(f"relationship:{relationship}")
        missing = char.get("missing_element")
        if missing == "means":
            known_facts.append("verification:Look for the actual weapon or toxin source; that is what would prove or disprove my involvement.")
        elif missing == "opportunity":
            known_facts.append("verification:Check the time-stamped alibi records; opportunity is the question.")
        elif missing == "motive":
            known_facts.append("verification:Look for a concrete reason I would want the victim dead; motive is the missing piece.")
        elif is_culprit:
            known_facts.append("verification:Compare my alibi and access records against the time of death.")

        npc = NPC(
            id=npc_id,
            name=char["name"],
            occupation=char.get("occupation", "Researcher"),
            location=room_id,
            personality=char.get("personality", "Guarded and professional."),
            alibi=char.get("alibi", "Unknown."),
            known_facts=known_facts,
            locked_facts=locked_facts,
            is_culprit=is_culprit,
        )
        npcs[npc_id] = npc

        if room_id in rooms and npc_id not in rooms[room_id].npcs:
            rooms[room_id].npcs.append(npc_id)

    return npcs

def _build_plot_points(crime_state: dict) -> dict[str, PlotPoint]:
    plot_points: dict[str, PlotPoint] = {}

    plot_points["arrive_at_scene"] = PlotPoint(
        id="arrive_at_scene",
        description="Arrive at the crime scene and examine the victim's body.",
        prerequisites=[],
        status=PlotPointStatus.AVAILABLE,
        location_hint="victim_office",
        effects={"scene_examined": True},
    )

    for clue in crime_state.get("clues", []):
        prereqs = ["arrive_at_scene"]
        if clue.get("prerequisite_clue_id"):
            prereqs.append(clue["prerequisite_clue_id"])

        plot_points[clue["id"]] = PlotPoint(
            id=clue["id"],
            description=f"Discover: {clue['description']}",
            prerequisites=prereqs,
            status=PlotPointStatus.LOCKED,
            location_hint=_slugify(clue.get("location", "victim_office")),
            effects={f"{clue['id']}_status": "discovered"},
        )

    for suspect in crime_state.get("suspects", []):
        pp_id = f"interview_{_slugify(suspect['name'])}"
        plot_points[pp_id] = PlotPoint(
            id=pp_id,
            description=f"Interview {suspect['name']} about their whereabouts.",
            prerequisites=["arrive_at_scene"],
            status=PlotPointStatus.LOCKED,
            location_hint=_slugify(suspect["name"]),
            effects={f"{_slugify(suspect['name'])}_status": "interviewed"},
        )

    from config import MIN_CLUES_TO_ACCUSE
    real_clues = [c["id"] for c in crime_state.get("clues", []) if not c.get("is_red_herring")]
    accusation_prereqs = real_clues[:MIN_CLUES_TO_ACCUSE]

    plot_points["reveal_culprit"] = PlotPoint(
        id="reveal_culprit",
        description="Confront and accuse the culprit with sufficient evidence.",
        prerequisites=accusation_prereqs,
        status=PlotPointStatus.LOCKED,
        location_hint="common_area",
        effects={"game_won": True},
    )

    return plot_points

def _build_causal_links(
    crime_state: dict,
    plot_points: dict[str, PlotPoint]
) -> list[CausalLink]:
    links: list[CausalLink] = []
    clue_map = {c["id"]: c for c in crime_state.get("clues", [])}

    for clue in crime_state.get("clues", []):
        prereq_id = clue.get("prerequisite_clue_id")
        if prereq_id:
            link = CausalLink(
                id=f"link_{prereq_id}_to_{clue['id']}",
                from_plot=prereq_id,
                to_plot=clue["id"],
                condition=f"The evidence from '{prereq_id}' is still accessible and intact",
                condition_key=f"{prereq_id}_intact",
                active=True,
            )
            links.append(link)

    for clue in crime_state.get("clues", []):
        if not clue.get("is_red_herring"):
            link = CausalLink(
                id=f"link_{clue['id']}_to_accusation",
                from_plot=clue["id"],
                to_plot="reveal_culprit",
                condition=f"Clue '{clue['id']}' has been properly documented",
                condition_key=f"{clue['id']}_documented",
                active=True,
            )
            links.append(link)

    return links

def _slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s_]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:40]


def _clue_to_object_name(description: str) -> str:
    desc = str(description or "").strip()
    low = desc.lower()

    patterns = [
        ("cologne", "lingering cologne scent"),
        ("residue", "suspicious residue"),
        ("neurotoxin", "fluorescent neurotoxin residue"),
        ("puncture", "tiny puncture mark"),
        ("air canister", "modified air canister and nozzle"),
        ("nozzle", "modified air canister and nozzle"),
        ("air gauge", "modified air canister and nozzle"),
        ("journal", "journal entry"),
        ("encrypted", "encrypted journal entry"),
        ("star chart", "torn star chart page"),
        ("cigar butt", "half-smoked cigar butt"),
        ("prescription pad", "blank prescription pad"),
        ("teacup", "half-empty teacup"),
        ("tea cup", "half-empty teacup"),
        ("button", "small button"),
        ("rug", "askew rug"),
        ("letter", "letter"),
        ("note", "note"),
        ("key", "key"),
        ("bottle", "dark glass bottle"),
        ("vial", "small vial"),
    ]
    for needle, label in patterns:
        if needle in low:
            if needle in {"button", "rug", "letter", "note", "key", "bottle", "vial"}:
                break
            return label

    text = re.sub(r"^(?:a|an|the)\s+", "", desc, flags=re.I)
    text = re.split(r"\b(?:found|discovered|lying|located)\b", text, maxsplit=1, flags=re.I)[0]

    chunks = [c.strip() for c in text.split(",") if c.strip()]
    bad_single = {"small", "faint", "tiny", "unusual", "strange", "single", "old", "worn", "dark", "blank", "torn"}
    if len(chunks) >= 2 and len(chunks[0].split()) == 1 and chunks[0].lower() in bad_single:
        text = chunks[0] + " " + chunks[1]
    else:
        text = chunks[0] if chunks else text

    words = text.split()
    stop_verbs = {"is", "are", "was", "were", "sits", "lies", "lying", "rests", "resting", "covers", "bearing", "with", "on", "in", "near", "at", "found", "discovered"}
    kept = []
    for w in words:
        clean = w.strip('.,;:"').lower()
        if kept and clean in stop_verbs:
            break
        kept.append(w.strip(".;:"))
        if len(kept) >= 5:
            break
    name = " ".join(kept).strip(' ,.;:')
    name = re.sub(r"\b\w+'s$", "", name).strip(" ,.;:")
    name = re.sub(r"\s+(?:on|in|at|near|of|from|by|under|above|beside)\s+\S+$", "", name, flags=re.I).strip(" ,.;:")

    if name.lower() in bad_single or len(name) < 3:
        for noun in ("button", "rug", "bottle", "vial", "letter", "note", "key", "cup", "pad", "cigar", "book", "envelope"):
            if noun in low:
                return f"{name} {noun}".strip()
        return "piece of evidence"
    return name[:55]


def _best_room_match(slug: str, room_ids: list[str]) -> str:
    for rid in room_ids:
        if rid in slug or slug in rid:
            return rid
    return "victim_office" if "victim_office" in room_ids else (room_ids[0] if room_ids else "entrance")


def _get_entry_room(rooms: dict[str, Room]) -> str:
    if "entrance" in rooms:
        return "entrance"
    if "corridor" in rooms:
        return "corridor"
    return next(iter(rooms))
