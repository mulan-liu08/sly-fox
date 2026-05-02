from __future__ import annotations

import re

from llm_client import call_llm
from config import RESPONSE_MODEL, RESPONSE_TEMP
from world.game_state import GameState
from engine.action_executor import ExecutionResult
from drama_manager.drama_manager import DMDecision


RESPONSE_SYSTEM = (
    "You are narrating a first-person murder mystery text adventure. "
    "Write in second-person present tense. Keep responses concise, complete, "
    "specific, and grounded in the provided game state. Never reveal the killer "
    "unless the player has correctly accused them. Never break the fourth wall."
)


def generate_response(
    action_verb: str,
    action_target: str | None,
    execution: ExecutionResult,
    dm_decision: DMDecision,
    game_state: GameState,
) -> str:
    hint = execution.narrative_hint or ""

    if hint.startswith("help:"):
        return hint[5:]

    if hint.startswith("inventory:"):
        items = hint[10:]
        if items == "empty":
            return "Your pockets are empty. You haven't picked anything up yet."
        return f"You're carrying: {items}."

    if hint.startswith("map:"):
        return hint[4:]

    if hint.startswith("exits:"):
        return hint.split(":", 1)[1]

    if hint.startswith("take:"):
        item = hint.split(":", 1)[1].strip() or "item"
        return f"You take the {item} and slip it into your coat pocket. It is now in your inventory."

    if hint.startswith("drop:"):
        item = hint.split(":", 1)[1].strip() or "item"
        return f"You set down the {item}. It is no longer in your inventory."

    if hint.startswith("room:"):
        parts = hint.split(":")
        room_id = parts[1].strip() if len(parts) > 1 and parts[1].strip() else game_state.player.location
        visit_status = parts[2].strip() if len(parts) > 2 else ""
        visited_override = False if visit_status == "new" else (True if visit_status == "visited" else None)
        return describe_room(game_state, room_id, visited_override=visited_override)

    if hint == "examine_room":
        return describe_room(game_state)

    if hint.startswith("examine_object:"):
        obj_id = hint.split(":", 1)[1]
        return _describe_object(obj_id, execution, game_state)

    if hint.startswith("examine_npc:"):
        npc_id = hint.split(":", 1)[1]
        return _describe_npc(npc_id, game_state)

    if hint.startswith("talk:"):
        return _describe_talk(hint, execution, game_state)

    if hint.startswith("show:"):
        return _describe_show(hint, game_state)

    if hint.startswith("accuse_correct:"):
        culprit = hint.split(":", 1)[1]
        return (
            f"You lay out the evidence piece by piece until {culprit} has nowhere left to hide. "
            "The final reconstruction is now clear."
        )

    if hint.startswith("accuse_wrong:") or hint.startswith("wrong_accusation:"):
        name = hint.split(":", 1)[1] if ":" in hint else "that suspect"
        return _wrong_accusation_feedback(name, game_state)

    if hint.startswith("accuse_too_early:"):
        counts = hint.split(":", 1)[1]
        found, needed = counts.split("/", 1) if "/" in counts else (counts, "more")
        return (f"You are not ready to make an accusation yet. You have {found} clue(s), but you need {needed}. "
                "Use HINT for the next lead, or CASE / SUSPECTS to review what you know so far.")

    if hint.startswith("search_reveals:"):
        revealed = hint.split(":", 1)[1].replace(",", ", ")
        return f"You search carefully and uncover something new: {revealed}."

    if hint == "search_nothing_new":
        return "You search the area methodically, but nothing new stands out right now."

    if hint.startswith("note_added:"):
        note = hint.split(":", 1)[1]
        return f"You jot that down in your notebook: {note}"

    if hint.startswith("use:"):
        parts = hint.split(":", 2)
        item_name = parts[2] if len(parts) > 2 else "it"
        return f"You try the {item_name}, but it does not reveal anything new yet."

    if hint.startswith("location:"):
        return hint.split(":", 1)[1]

    if hint.startswith("case:"):
        return hint.split(":", 1)[1]

    if hint.startswith("evidence:"):
        return hint.split(":", 1)[1]

    if hint.startswith("suspects:"):
        return hint.split(":", 1)[1]

    if hint.startswith("hint:"):
        return hint.split(":", 1)[1]

    if hint.startswith("case_answer:"):
        return hint.split(":", 1)[1]

    if not execution.success:
        return hint or f"You try to {action_verb}, but nothing comes of it."

    if _is_plain_engine_message(hint):
        return hint
    prompt = _build_prompt(action_verb, action_target, execution, dm_decision, game_state)
    try:
        response = call_llm(
            prompt=prompt,
            model_name=RESPONSE_MODEL,
            system_instruction=RESPONSE_SYSTEM,
            temperature=RESPONSE_TEMP,
            max_output_tokens=300,
        ).strip()
        return _ensure_complete_sentence(response, fallback=_fallback_response(hint, execution, game_state))
    except Exception:
        return _fallback_response(hint, execution, game_state)

def describe_room(game_state: GameState, room_id: str | None = None, visited_override: bool | None = None) -> str:
    rid = room_id or game_state.player.location
    room = game_state.rooms.get(rid)
    if not room:
        return "You are not sure where you are."

    is_visited = room.visited if visited_override is None else visited_override
    visited = " (you've been here before)" if is_visited else ""

    exits = []
    special = []
    for direction, dest_id in room.exits.items():
        dest = game_state.rooms.get(dest_id)
        dest_name = dest.name if dest else dest_id.replace("_", " ").title()
        clean_direction = direction.replace("_", " ")
        if clean_direction.startswith(("examine ", "inspect ", "read ", "open ", "use ")):
            special.append(f"{clean_direction} → {dest_name}")
        else:
            exits.append(f"{clean_direction} → {dest_name}")
    exit_str = ", ".join(exits) if exits else "none"
    special_str = ", ".join(special) if special else "none"

    objects = []
    for oid in room.objects:
        obj = game_state.objects.get(oid)
        objects.append(obj.name if obj else oid.replace("_", " "))
    obj_str = ", ".join(objects) if objects else "nothing of note"

    people = []
    for nid in room.npcs:
        npc = game_state.npcs.get(nid)
        if npc:
            people.append(f"{npc.name} ({npc.occupation})")
        else:
            people.append(nid.replace("_", " ").title())
    npc_str = ", ".join(people) if people else "no one"

    return (
        f"**{room.name}**{visited}\n"
        f"{room.description}\n"
        f"Exits: {exit_str}\n"
        f"Objects here: {obj_str}\n"
        f"People here: {npc_str}"
    )


def _describe_object(obj_id: str, execution: ExecutionResult, gs: GameState) -> str:
    obj = gs.objects.get(obj_id)
    if not obj:
        return "You examine it carefully, but nothing useful stands out."

    lines = [f"You examine the {obj.name}. {obj.description}"]

    if execution.clue_discovered:
        clue = _get_clue(execution.clue_discovered, gs)
        if clue:
            points_to = clue.get("points_to")
            if points_to == "culprit":
                lines.append(_culprit_clue_reason(clue, gs))
            elif points_to:
                lines.append(_clue_implication_reason(clue, gs))
    return "\n".join(line for line in lines if line)


def _describe_npc(npc_id: str, gs: GameState) -> str:
    npc = gs.npcs.get(npc_id)
    if not npc:
        return "They are hard to read from here."
    return (
        f"{npc.name} is here, {npc.occupation}. "
        f"{npc.personality or 'They seem guarded.'}"
    )


def _describe_talk(hint: str, execution: ExecutionResult, gs: GameState) -> str:
    parts = hint.split(":", 4)
    npc_id = parts[1] if len(parts) > 1 else ""
    name = parts[2] if len(parts) > 2 else "The witness"
    raw_alibi = parts[3] if len(parts) > 3 else "They claim they do not know anything useful."
    facts = parts[4] if len(parts) > 4 else ""
    npc = gs.npcs.get(npc_id)

    if not npc:
        return f"{name} gives you a guarded statement, but you cannot read much from it."

    alibi = _public_alibi_for(npc, raw_alibi, gs)
    relationship = _relationship_for(npc, gs)
    verification = _verification_guidance(npc, gs)

    safe_facts: list[str] = []
    for fact in facts.split(" | ")[:2]:
        fact = fact.strip()
        if not fact or _should_hide_interview_fact(fact):
            continue
        safe_fact = _first_person_statement(_strip_meta_reasoning(fact), npc, gs)
        if safe_fact and not _should_hide_interview_fact(safe_fact):
            safe_facts.append(safe_fact)

    if execution.npc_interviewed is None:
        short_aliases = [
            f"{npc.name} meets your gaze evenly. \"My statement stands as given. I have nothing to add.\"",
            f"{npc.name} sighs. \"I have already told you everything I know.\"",
            f"{npc.name} repeats their account without new detail. The story is unchanged.",
        ]
        import hashlib
        idx = int(hashlib.md5(npc.id.encode()).hexdigest(), 16) % len(short_aliases)
        return short_aliases[idx]
    llm_response = _try_llm_interview(npc, alibi, relationship, verification, safe_facts, gs)
    if llm_response:
        return llm_response

    lines = [_npc_intro(npc), f"\"{alibi}\""]
    if relationship:
        lines.append(f"{_speech_tag(npc)} \"{relationship}\"")
    if verification:
        lines.append(f"{_speech_tag(npc)} \"{verification}\"")
    for fact in safe_facts:
        lines.append(f"{_speech_tag(npc)} \"{fact}\"")
    return "\n".join(lines)


def _try_llm_interview(npc, alibi: str, relationship: str, verification: str, safe_facts: list[str], gs: GameState) -> str | None:
    victim = _victim_short(gs)
    case_place = gs.crime_state.get("setting", {}).get("location", "the crime scene")
    prompt = f"""
Write a short in-character interview response for a text murder mystery.

Victim reference: {victim}
Setting: {case_place}
Speaker name: {npc.name}
Speaker occupation: {npc.occupation}
Speaker personality: {npc.personality or 'guarded'}
Public alibi to state: {alibi}
Safe relationship statement to state, if useful: {relationship}
Safe verification/challenge line to state, if useful: {verification}
Other safe facts: {safe_facts}

Rules:
- Output JSON only with keys: intro, lines.
- intro: one sentence describing demeanor, using the speaker name and no gendered pronoun unless certain.
- lines: 2 to 4 first-person quoted statements, without quote marks.
- Use first person for the speaker: I, me, my, myself. Fully rewrite awkward report-style alibis; do not mechanically replace pronouns.
- Do not reveal contradictions, hidden evidence, the culprit, secret guilt, or detective-only case-file analysis.
- Do not use phrases like "this sounds plausible", "case file", "means/motive/opportunity", or "complicated connection".
- Keep it natural for the generated setting; do not assume labs, spectrographs, toxins, or modern access logs unless they are in the public text above.
""".strip()
    try:
        data = call_llm(
            prompt=prompt,
            model_name=RESPONSE_MODEL,
            system_instruction="You write safe, natural NPC dialogue for an interactive mystery. Never leak hidden culprit facts.",
            expect_json=True,
            temperature=0.65,
            max_output_tokens=500,
        )
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    intro = str(data.get("intro", "")).strip()
    lines = data.get("lines", [])
    if not isinstance(lines, list):
        return None
    cleaned_lines: list[str] = []
    for line in lines[:4]:
        line = _clean_dialogue_line(str(line), npc, gs)
        if line:
            cleaned_lines.append(line)
    intro = _strip_meta_reasoning(intro)
    if not intro or _dialogue_unsafe(intro) or len(cleaned_lines) < 1:
        return None
    if any(_dialogue_unsafe(line) for line in cleaned_lines):
        return None
    return "\n".join([intro] + [f"\"{line}\"" for line in cleaned_lines])


def _dialogue_unsafe(text: str) -> bool:
    low = str(text).lower()
    banned = (
        "this sounds plausible", "case file", "detective-only", "hidden contradiction",
        "culprit", "killer", "i killed", "i murdered", "i poisoned", "i stabbed",
        "security logs show", "logs show", "unlogged exit", "secretly", "in truth",
        "actually", "unknown to", "means/motive/opportunity", "complicated connection",
    )
    return any(b in low for b in banned)


def _clean_dialogue_line(text: str, npc, gs: GameState) -> str:
    text = _strip_meta_reasoning(text)
    text = text.strip().strip('"“”')
    text = _first_person_statement(text, npc, gs)
    text = _repair_first_person_grammar(text)
    text = _normalize_sentence_punctuation(text)
    return "" if _dialogue_unsafe(text) else text


def _public_alibi_for(npc, raw_alibi: str, gs: GameState) -> str:
    clean = _strip_hidden_contradictions(raw_alibi)
    clean = _strip_meta_reasoning(clean)
    if not clean:
        clean = "I was elsewhere during the critical window."
    return _first_person_statement(clean, npc, gs)


def _should_hide_interview_fact(fact: str) -> bool:
    low = fact.lower()
    hidden_markers = (
        "security logs show", "logs show", "unlogged exit", "back service door",
        "maintenance tunnel", "academic fraud", "celestia algorithm", "murder",
        "killer", "culprit", "i was in my lab during the critical window",
        "you should check the", "my connection to", "relationship:",
        "verification:", "this sounds plausible", "this suggests", "this indicates",
        "hidden", "secretly", "in truth", "case file",
    )
    return any(marker in low for marker in hidden_markers)


def _npc_intro(npc) -> str:
    name = npc.name
    personality = (npc.personality or "").lower()
    occupation = (npc.occupation or "").lower()
    if any(k in personality for k in ("nervous", "anxious", "shy", "timid")):
        return f"{name} answers quietly, choosing each word with visible care."
    if any(k in personality for k in ("pompous", "arrogant", "proud", "competitive")):
        return f"{name} straightens, offended but precise."
    if any(k in personality for k in ("calm", "composed", "controlled", "cold")):
        return f"{name} remains composed, giving you a measured answer."
    if any(k in personality for k in ("gruff", "military", "security", "protective")) or "security" in occupation:
        return f"{name} squares their shoulders and gives you the facts."
    if any(k in occupation for k in ("servant", "valet", "housekeeper", "assistant")):
        return f"{name} answers carefully, with the caution of someone used to being overheard."
    return f"{name} answers after a guarded pause."


def _speech_tag(npc) -> str:
    return f"{npc.name} adds,"


def _first_person_statement(text: str, npc, gs: GameState | None = None) -> str:
    if not text:
        return text
    text = str(text).strip()
    text = _strip_meta_reasoning(text)
    name = npc.name or ""
    first = name.split()[0].strip('"') if name else ""
    last = name.split()[-1].strip('"') if name else ""

    text = re.sub(r"^(?:claims?|claimed|stated|states|says|said)\s+(?:that\s+)?", "", text, flags=re.I).strip()
    text = re.sub(r"^(?:was|were)\b", "I was", text, flags=re.I).strip()

    victim_name = ""
    if gs:
        victim_name = str(gs.crime_state.get("victim", {}).get("name", "") or "").strip()
    victim_tokens = set(re.findall(r"[A-Za-z]+", victim_name))

    for token in sorted({name, first, last}, key=len, reverse=True):
        if not token:
            continue
        if token in victim_tokens and token != name:
            continue
        text = re.sub(r"\b" + re.escape(token) + r"\b", "I", text)

    replacements = [
        (r"\bherself\b", "myself"),
        (r"\bhimself\b", "myself"),
        (r"\bthemselves\b", "myself"),
        (r"\bher\s+own\b", "my own"),
        (r"\bhis\s+own\b", "my own"),
        (r"\btheir\s+own\b", "my own"),
        (r"\bher\b", "my"),
        (r"\bhis\b", "my"),
        (r"\btheir\b", "my"),
        (r"\bshe\b", "I"),
        (r"\bhe\b", "I"),
        (r"\bthey\b", "I"),
    ]
    for pat, repl in replacements:
        text = re.sub(pat, repl, text, flags=re.I)

    text = _repair_first_person_grammar(text)
    text = _normalize_sentence_punctuation(text)
    return text


def _repair_first_person_grammar(text: str) -> str:
    repairs = {
        "I were": "I was",
        "I has": "I have",
        "I had locked myself": "I had locked myself",
        "I does": "I do",
        "I claims": "I claim",
        "I claim I was": "I was",
        "I stated I had": "I had",
        "I stated I was": "I was",
        "my over": "me over",
        "blackmailing my": "blackmailing me",
        "threatening my": "threatening me",
        "accusing my": "accusing me",
        "ruin my reputation": "ruin my reputation",
        "to my ": "to me ",
        "for my ": "for me ",
        "with my ": "with me ",
        "I was one of my senior researchers": "I was one of the senior researchers",
        "I was my senior researcher": "I was a senior researcher",
        "I did not leave my lab during my time": "I did not leave my lab during that time",
        "saw my ": "saw me ",
        "saw my,": "saw me,",
        "who saw my": "who saw me",
        "heard my ": "heard me ",
        "watched my ": "watched me ",
    }
    for old, new in repairs.items():
        text = text.replace(old, new)
    text = re.sub(r"\bI was in my ([^.,;]+), alone, during my time\b", r"I was in my \1 during that time", text)
    text = re.sub(r"\bI was in my ([^.,;]+), alone, during the time\b", r"I was in my \1 during the time", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_sentence_punctuation(text: str) -> str:
    text = str(text or "").strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([.!?]){2,}$", r"\1", text)
    if text and text[-1] not in ".!?":
        text += "."
    return text


def _relationship_for(npc, gs: GameState) -> str:
    victim = _victim_short(gs)
    culprit = gs.crime_state.get("culprit", {})

    if npc.is_culprit:
        rel = _safe_relationship_summary(culprit.get("relationship_to_victim") or "", npc, gs)
        if rel:
            return rel
        return f"{victim} and I had history, but that does not make me a murderer."

    for suspect in gs.crime_state.get("suspects", []):
        if _norm(suspect.get("name", "")) == _norm(npc.name):
            rel = _safe_relationship_summary(suspect.get("relationship_to_victim", ""), npc, gs)
            return rel
    return ""


def _safe_relationship_summary(raw: str, npc, gs: GameState) -> str:
    victim = _victim_short(gs)
    text = _strip_meta_reasoning(str(raw or "").strip())
    low = text.lower()
    if not text:
        return ""
    if any(k in low for k in ("blackmail", "fraud", "affair", "secret", "scandal", "threat", "inheritance", "debt", "stole", "ruin", "resourceful", "resourcefulness", "wrong end", "rival")):
        return f"{victim} and I had a strained history. Some of it is private, but I am not hiding a murder."
    fp = _first_person_statement(text, npc, gs).rstrip(".")
    if fp.lower().startswith("i ") or fp.lower().startswith("my "):
        return fp + "."
    return f"My connection to {victim}: {fp}."


def _verification_guidance(npc, gs: GameState) -> str:
    victim = _victim_short(gs)
    culprit = gs.crime_state.get("culprit", {})
    if npc.is_culprit:
        return _culprit_public_verification(culprit, victim)
    missing = _missing_element_for(npc, gs)
    if missing == "means":
        return "If you doubt me, find the actual weapon or method. Without that, you still have no proof I had any way to commit the murder."
    if missing == "opportunity":
        return f"If you doubt me, check the timing. If I could not reach {victim} during the critical window, the theory falls apart."
    if missing == "motive":
        return f"If you doubt me, find a concrete reason I would want {victim} dead. Without motive, suspicion is only noise."
    return "If you doubt me, compare my alibi against the physical evidence."


def _strip_meta_reasoning(text: str) -> str:
    if not text:
        return ""
    pieces = re.split(r"(?<=[.!?])\s+", str(text).strip())
    banned_starts = (
        "this sounds", "this suggests", "this indicates", "this implies",
        "this would", "it sounds plausible", "plausible as", "servants often",
        "detective", "case file", "the clue", "the evidence",
    )
    kept = []
    for piece in pieces:
        low = piece.strip().lower()
        if not low:
            continue
        if low.startswith(banned_starts) or any(b in low for b in ("sounds plausible", "would imply", "this is suspicious")):
            continue
        kept.append(piece.strip())
    return " ".join(kept).strip()

def _victim_short(gs: GameState) -> str:
    victim = gs.crime_state.get("victim", {}) if gs else {}
    name = str(victim.get("name") or "the victim").strip()
    if not name or name.lower() == "the victim":
        return "the victim"
    parts = name.split()
    if len(parts) >= 2 and parts[0].rstrip('.').lower() in {"dr", "prof", "professor", "lord", "lady", "sir", "dame", "mr", "mrs", "ms", "miss"}:
        return f"{parts[0]} {parts[-1]}"
    return parts[-1]


def _strip_hidden_contradictions(text: str) -> str:
    if not text:
        return ""
    raw = str(text).strip()
    pieces = re.split(r"(?<=[.!?])\s+|;\s+", raw)
    hidden_markers = (
        "but ", "however", "security logs", "logs show", "camera footage shows",
        "gps", "unlogged", "contradict", "actually", "in truth", "unknown to",
        "detective", "reveals", "evidence shows", "leads directly", "hidden",
        "secretly", "falsified", "fraud", "stole", "murder", "killer", "culprit",
    )
    kept: list[str] = []
    for piece in pieces:
        clean = piece.strip()
        if not clean:
            continue
        low = clean.lower()
        if kept and any(marker in low for marker in hidden_markers):
            break
        if not kept and low.startswith(("but ", "however")):
            break
        kept.append(clean)
        if len(kept) >= 2:
            break
    return " ".join(kept).strip() or raw


def _token_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", str(text).lower()) if len(w) > 3}


def _overlaps(a: str, b: str) -> bool:
    if not a or not b:
        return False
    wa = _token_words(a)
    wb = _token_words(b)
    if not wa or not wb:
        return False
    return len(wa & wb) >= 2


def _looks_like_motive(text: str) -> bool:
    low = str(text).lower()
    return any(k in low for k in (
        "motive", "fraud", "blackmail", "inheritance", "will", "debt", "affair",
        "threat", "expose", "rivalry", "algorithm", "credit", "revenge", "jealous",
        "fortune", "business", "secret", "letter", "journal", "diary",
    ))


def _looks_like_weapon(text: str) -> bool:
    low = str(text).lower()
    return any(k in low for k in (
        "weapon", "knife", "gun", "pistol", "revolver", "poison", "toxin", "neurotoxin",
        "dart", "needle", "canister", "nozzle", "gauge", "rope", "cord", "candlestick",
        "vial", "powder", "glass", "blade", "syringe",
    ))


def _looks_like_body_or_method(text: str) -> bool:
    low = str(text).lower()
    return any(k in low for k in (
        "body", "wound", "puncture", "bruise", "blood", "autopsy", "cause of death",
        "cardiac", "strangled", "suffocated", "shot", "stabbed", "poison", "method",
        "residue", "mark", "burn", "fracture",
    ))


def _relationship_from_motive(motive: str) -> str:
    text = str(motive or "").strip()
    if not text:
        return ""
    first = re.split(r"(?<=[.!?])\s+|;\s+", text)[0].strip()
    return first[:180]


def _culprit_public_verification(culprit: dict, victim: str) -> str:
    alibi = str(culprit.get("alibi") or "").lower()
    opportunity = str(culprit.get("opportunity") or "").lower()
    means = str(culprit.get("means") or "").lower()
    if any(k in alibi for k in ("lab", "instrument", "spectro", "equipment")):
        return "If you want to verify my alibi, check the instrument logs and access records. They should show I was working, not roaming around."
    if any(k in alibi for k in ("study", "library", "office", "desk")):
        return f"If you doubt me, check who saw me and when. I had no reason to leave my work to harm {victim}."
    if any(k in alibi for k in ("kitchen", "lounge", "dining")):
        return "If you doubt me, ask the staff who saw me that evening. I was nowhere near the killing."
    if any(k in means for k in ("poison", "toxin", "chemical", "vial")):
        return "If you doubt me, find the source of the poison. Speculation is not proof."
    if opportunity:
        return "If you doubt me, check the timing. My movements will speak for themselves."
    return "If you doubt me, test the evidence. Suspicion is not the same as proof."


def _wrong_accusation_weak_point(npc, missing: str, gs: GameState) -> str:
    victim = _victim_short(gs)
    missing = (missing or "").lower()
    if missing == "means":
        return f"The weak point is means: you have not shown how {npc.name} could have physically carried out the killing."
    if missing == "opportunity":
        return f"The weak point is opportunity: the timing evidence still needs to place {npc.name} near {victim} during the critical window."
    if missing == "motive":
        return f"The weak point is motive: access alone is not enough without a reason {npc.name} would want {victim} dead."
    return f"The evidence against {npc.name} is still missing a complete means, motive, and opportunity chain."



def _culprit_clue_reason(clue: dict, gs: GameState) -> str:
    culprit_info = gs.crime_state.get("culprit", {}) or {}
    culprit = culprit_info.get("name", "the strongest suspect")
    victim = _victim_short(gs)
    desc = str(clue.get("description", "")).lower()

    method      = (culprit_info.get("method", "") or "").lower()
    means       = (culprit_info.get("means", "") or "").lower()
    opportunity = (culprit_info.get("opportunity", "") or "").lower()
    motive      = (culprit_info.get("motive", "") or "").lower()

    desc_words  = {w for w in re.findall(r"[a-zA-Z]{4,}", desc)}
    method_words = {w for w in re.findall(r"[a-zA-Z]{4,}", method)}
    means_words = {w for w in re.findall(r"[a-zA-Z]{4,}", means)}
    opp_words   = {w for w in re.findall(r"[a-zA-Z]{4,}", opportunity)}
    mot_words   = {w for w in re.findall(r"[a-zA-Z]{4,}", motive)}

    if desc_words & method_words:
        return (f"This connects to how {victim} died. It is consistent with "
                f"{culprit}'s method and is worth comparing against their alibi.")
    if desc_words & means_words:
        return (f"This connects to the means available to {culprit}: "
                f"it is consistent with their known access and capabilities.")
    if desc_words & opp_words:
        return (f"This bears on opportunity — it helps establish who had access "
                f"to the victim during the critical window.")
    if desc_words & mot_words:
        return (f"This is relevant to motive: it connects to why {culprit} "
                f"may have wanted {victim} dead.")
    return (f"This evidence has not been fully explained and is consistent with "
            f"{culprit}'s profile. Compare it against their alibi.")

def _clue_implication_reason(clue: dict, gs: GameState) -> str:
    points_to = clue.get("points_to")
    if not points_to or points_to == "culprit":
        return ""

    desc = str(clue.get("description", "")).lower()
    is_red_herring = clue.get("is_red_herring", False)
    victim = _victim_short(gs)

    suspect = next(
        (s for s in gs.crime_state.get("suspects", []) if s.get("name") == points_to),
        None
    )
    if not suspect:
        return f"At first glance, it raises questions about {points_to}."

    relationship = (suspect.get("relationship_to_victim") or "").split(".")[0].strip()
    occupation   = (suspect.get("occupation") or "").strip()
    missing      = (suspect.get("missing_element") or "").strip()

    name_tokens  = [t for t in re.findall(r"[a-zA-Z]{4,}", points_to.lower())]
    names_in_desc = any(t in desc for t in name_tokens)

    if names_in_desc:
        base = f"The evidence directly names or references {points_to}"
    elif relationship:
        base = f"Given {points_to}'s relationship to {victim} ({relationship}), this is worth examining"
    elif occupation:
        base = f"This is consistent with {points_to}'s access as {occupation}"
    else:
        base = f"This raises questions about {points_to}'s presence near the scene"

    if is_red_herring:
        return (f"At first glance, {base.lower()}, though further investigation will show "
                f"there is an innocent explanation.")
    else:
        if missing == "means":
            suffix = f" You still need to establish how {points_to} could have committed the crime."
        elif missing == "opportunity":
            suffix = f" You still need to place {points_to} at the scene during the critical window."
        elif missing == "motive":
            suffix = f" You still need a concrete reason why {points_to} would want {victim} dead."
        else:
            suffix = " It is still circumstantial until means, motive, and opportunity line up."
        return f"{base}. {suffix.strip()}"


def _wrong_accusation_feedback(name: str, gs: GameState) -> str:
    accused = None
    wanted = _norm(name)
    for npc in gs.npcs.values():
        if wanted and (wanted in _norm(npc.name) or wanted in _norm(npc.id)):
            accused = npc
            break

    culprit = gs.crime_state.get("culprit", {}).get("name", "the true culprit")
    real_clues = []
    red_herrings = []
    for clue_id in gs.player.discovered_clues:
        clue = _get_clue(clue_id, gs)
        if not clue:
            continue
        obj = next((o for o in gs.objects.values() if o.clue_id == clue_id), None)
        clue_name = obj.name if obj else clue_id.replace("_", " ")
        if clue.get("is_red_herring"):
            red_herrings.append((clue_name, clue.get("points_to")))
        elif clue.get("points_to") == "culprit":
            real_clues.append(clue_name)

    lines = [f"You accuse {name}, but the evidence does not hold together."]
    if accused:
        missing = _missing_element_for(accused, gs)
        if missing:
            lines.append(_wrong_accusation_weak_point(accused, missing, gs))
        if red_herrings:
            rh_names = ", ".join(n for n, target in red_herrings if target and _norm(str(target)) in _norm(accused.name))
            if rh_names:
                lines.append(f"The clue pointing toward {accused.name} ({rh_names}) may be circumstantial or misleading.")
    if real_clues:
        lines.append(f"Your strongest evidence so far is: {', '.join(real_clues)}.")
    lines.append("Type CASE or SUSPECTS to review the reasoning, then accuse the suspect with the strongest means, motive, and opportunity chain.")
    return "\n".join(lines)


def _missing_element_for(npc, gs: GameState) -> str | None:
    for suspect in gs.crime_state.get("suspects", []):
        if _norm(suspect.get("name", "")) == _norm(npc.name):
            return suspect.get("missing_element")
    return None


def _norm(text: str) -> str:
    return "".join(ch for ch in str(text).lower() if ch.isalnum())

def _describe_show(hint: str, gs: GameState) -> str:
    parts = hint.split(":", 5)
    obj_id = parts[1] if len(parts) > 1 else ""
    npc_id = parts[2] if len(parts) > 2 else ""
    npc_name = parts[3] if len(parts) > 3 else "the witness"
    obj = gs.objects.get(obj_id)
    obj_name = obj.name if obj else "the evidence"
    if ":reveals:" in hint:
        fact = hint.split(":reveals:", 1)[1]
        return f"You show {obj_name} to {npc_name}. Their composure slips. \"{fact}\""
    return f"You show {obj_name} to {npc_name}, but it does not shake loose anything new."


def _get_clue(clue_id: str, gs: GameState) -> dict | None:
    return next((c for c in gs.crime_state.get("clues", []) if c.get("id") == clue_id), None)


def _build_prompt(action_verb: str, action_target: str | None, execution: ExecutionResult, dm_decision: DMDecision, gs: GameState) -> str:
    room = gs.rooms.get(gs.player.location)
    room_name = room.name if room else "unknown location"
    lines = [
        f"Location: {room_name}",
        f"Action: {action_verb} {action_target or ''}",
        f"Succeeded: {execution.success}",
        f"Narrative hint: {execution.narrative_hint}",
        f"Clues found: {len(gs.player.discovered_clues)}",
    ]
    if dm_decision.action == "accommodate" and dm_decision.message:
        lines.append(f"Accommodation: {dm_decision.message}")
    return "\n".join(lines) + "\n\nWrite 1-3 complete sentences."


def _is_plain_engine_message(hint: str) -> bool:
    if not hint:
        return False
    structured_prefixes = (
        "examine_object:", "examine_npc:", "examine_room", "talk:", "show:",
        "accuse_correct:", "accuse_wrong:", "wrong_accusation:", "accuse_too_early:",
        "search_reveals:", "search_nothing_new", "help:", "inventory:", "map:",
        "take:", "drop:", "room:", "note_added:", "use:", "location:",
        "case:", "evidence:", "suspects:", "hint:", "case_answer:", "exits:",
    )
    return not hint.startswith(structured_prefixes) and hint[-1:] in ".!?"


def _ensure_complete_sentence(response: str, fallback: str) -> str:
    response = (response or "").strip()
    if not response:
        return fallback
    if response[-1] not in ".!?\"'”’":
        return fallback
    return response


def _fallback_response(hint: str, result: ExecutionResult, gs: GameState) -> str:
    if not result.success:
        return hint or "You try, but nothing comes of it."
    if hint.startswith("room:") or hint == "examine_room":
        return describe_room(gs)
    if result.clue_discovered:
        clue = _get_clue(result.clue_discovered, gs)
        return f"You have found evidence: {clue['description']}" if clue else "You've found something significant."
    return hint if hint else "Done."
