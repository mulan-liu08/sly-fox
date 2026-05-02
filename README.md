# Sly Fox — Interactive Mystery

**Team name:** Sly Fox   
**Project template:** Intervention and Accommodation

Sly Fox is a Python text-adventure murder mystery game. The player takes the role of **Detective Morgan Reyes**, explores a generated crime scene, collects evidence, interviews suspects, and eventually accuses the culprit. The system uses a Phase I crime-story generator to produce the hidden murder-mystery state, then turns that state into a playable text game with rooms, objects, NPCs, plot points, causal links, and a drama manager.

The project follows the **Intervention and Accommodation** template: player actions are interpreted as **constituent**, **consistent**, or **exceptional**. Constituent actions advance the detective story, consistent actions are allowed without advancing the plot, and exceptional actions threaten causal links or solvability. When possible, the drama manager accommodates exceptional actions by repairing the story so the investigation can still continue.

---

## What the system does

At a high level, the game:

1. Generates or loads a structured crime state.
2. Builds a navigable text-game world from that crime state.
3. Interprets open-ended player commands.
4. Executes valid actions against the game state.
5. Uses a drama manager to detect exceptional actions and intervene.
6. Generates narrative responses and game-state feedback.
7. Ends when the player correctly accuses the culprit or the mystery becomes unsolvable.

The player can type commands such as:

```text
look
map
north
search room
examine residue
take access pass
talk to Dr. Reed
show residue to Dr. Reed
case
suspects
hint
accuse Dr. Reed
destroy note
quit
```

Commands are not menu-based. Short, natural-language commands work best.

---

## Walkthrough Guide
An entire walkthrough of the interactive game from start to end is in the `walkthrough.txt` file. Below are highlighted points of the walkthrough that point out user actions and DM's responses and possible intervention.

*Note: the transcript of the original walkthrough shown in the demo video was lost, so the walkthrough here does not match the one in the demo video exactly. However, all required elements (e.g., DM intervention) are still present in this walkthrough and much of the story remains the same.*

### Story setup
At the beginning, we are told the opening scene, our identity, and our starting location. At each location, we are given other locations we can move to, objects to interact with, and people that we can talk to. The player types their chosen action preceded by the `>` prompt character. In the case below, the player chooses to go east into the **Manor's Common Area**.

```
  **Grand Entrance Hall**
  The imposing entrance hall of Blackwood Manor, echoing with forgotten
  footsteps. A grand staircase ascends into shadow, and heavy oak doors
  lead further into the estate.
  Exits: east → Manor's Common Area, up → Grand Staircase Landing
  Objects here: brass house key
  People here: no one


────────────────────────────────────────

  > go east
```

### Interact with NPCs
At any location, if an NPC is present, we can choose to talk to them. 

```
  **Dusty Main Corridor**
  A long, winding corridor lined with faded portraits of stern-faced
  ancestors. The air is still and carries a faint scent of old wood and
  dust.
  Exits: south → Manor's Common Area, west → Dim Security Office, east →
  Victim's Private Office, north → Back Corridor Near Study
  Objects here: nothing of note
  People here: Eleanor Vance (Researcher)

────────────────────────────────────────

  > talk to eleanor
  ...
  Eleanor Vance remains composed, giving you a measured answer.
  "I was in the library organizing a newly arrived collection of rare
  medieval manuscripts, a task that would keep my isolated and away from
  the main drawing-room during the time of the murder."
  Eleanor Vance adds, "Lord Finch and I had history, but that does not
  make me a murderer."
  Eleanor Vance adds, "If you doubt me, check who saw me and when. I had
  no reason to leave my work to harm Lord Finch."
```
### Getting unstuck
If a player has "wandered around" for too long without doing anything significant, the Drama Manager provides a hint for where to find the next clue.

```
  > go west
  ...
  **Dim Security Office**
  A small, cluttered room filled with outdated surveillance equipment.
  Monitors flicker with static, casting an eerie glow on forgotten
  files.
  Exits: east → Dusty Main Corridor
  Objects here: nothing of note
  People here: Dr. Elias Thorne (Lord Finch's Personal Physician)

    *Next lead: go east, then go north, then go north to reach Lord
  Finch's Study Entrance, then examine the small ornate silver locket.*
```

### Examining objects
Players may examine any objects that are present at a location and log them as evidence.

```
  **Lord Finch's Study Entrance**
  The grand study of Lord Finch, filled with leather-bound books and a
  heavy oak desk. A faint scent of brandy lingers in the air, and a
  large, ornate decanter sits prominently.
  Exits: south → Back Corridor Near Study
  Objects here: small ornate silver locket
  People here: no one

────────────────────────────────────────

  > examine small ornate silver locket
  ...
  You examine the small ornate silver locket. A small, ornate silver
  locket, slightly tarnished, found partially hidden under Lord Finch's
  study desk. Inside, it contains a faded photograph of a young girl and
  a tiny, almost illegible inscription: 'E.V.'
  This connects to how Lord Finch died. It is consistent with Eleanor
  Vance's method and is worth comparing against their alibi.

EVIDENCE LOGGED: small ornate silver locket
     A small, ornate silver locket, slightly tarnished, found partially
     hidden under Lord Finch's study desk. Inside, it contains a faded
     photograph of a young girl and a tiny, almost illegible
     inscription: 'E.V.'
     Clues found: 1 | Need 2 more to make accusation
```

### DM Intervention for Exceptional Action
If a player wants to perform an exceptional (story-breaking) action, then the DM will prevent them from doing so.

```
  > destroy the silver locket
  ...
  You consider trying to 'destroy the silver locket' but aren't sure
  how.
```

### DM Allowance for Consistent Action
If a player's action does not harm the story, the DM allows it to happen.

```
  > take a nap
  ...
  Time passes. The hum of the facility continues.
```

### Block early accusation
The DM ensures that the player has enough evidence before accusing someone.

```
  > accuse eleanor vance
  ...
  You are not ready to make an accusation yet. You have 1 clue(s), but
  you need 3. Use HINT for the next lead, or CASE / SUSPECTS to review
  what you know so far.
```

### Review Case
The player can review everything they've gathered so far.

```
  > case
  ...
  Detective's case board

  Evidence logged:
  1. small ornate silver locket — strong case evidence. A small, ornate
  silver locket, slightly tarnished, found partially hidden under Lord
  Finch's study desk. Inside, it contains a faded photograph of a young
  girl and a tiny, almost illegible inscription: 'E.V.' This connects to
  how Lord Finch was killed: it is consistent with Eleanor Vance's
  method and warrants closer scrutiny of their access.
  2. faint sweet almond-like scent lingering — strong case evidence. A
  faint, sweet almond-like scent lingering on a discarded, embroidered
  handkerchief found near the study's back entrance. This scent is
  characteristic of Belladonna. This connects to how Lord Finch was
  killed: it is consistent with Eleanor Vance's method and warrants
  closer scrutiny of their access.
  3. half-empty bottle of Chloral Hydrate — circumstantial lead. A half-
  empty bottle of Chloral Hydrate, a potent sedative, found in Dr.
  Thorne's medical bag, along with a syringe. The evidence directly
  names or references Dr. Elias Thorne, though further investigation
  will show this is circumstantial. What appears to implicate them has
  an innocent explanation.

  Suspect board:
  - Eleanor Vance (interviewed): suspicion 5/5 — small ornate silver
  locket fits the hidden method or motive connected to Eleanor Vance;
  faint sweet almond-like scent lingering fits the hidden method or
  motive connected to Eleanor Vance; has a complete
  means/motive/opportunity profile.
  - Dr. Elias Thorne (interviewed): suspicion 2/5 — half-empty bottle of
  Chloral Hydrate raises questions about this suspect; half-empty bottle
  of Chloral Hydrate names or implies this suspect.
  - Lady Beatrice Finch (interviewed): suspicion 0/5 — no direct
  evidence logged yet.
  - Arthur Davies (interviewed): suspicion 0/5 — no direct evidence
  logged yet.

  You have enough evidence to accuse. Strongest current lead: Eleanor
  Vance.
  Try: accuse Eleanor Vance

  Suggested next step:
  You have enough evidence to make an accusation. Review CASE or
  SUSPECTS if needed, then try: accuse Eleanor Vance.
```
### Insufficient accusation
```
  > accuse dr. elias thorne
  ...
  You accuse Dr. Elias Thorne, but the evidence does not hold together.
  The weak point is opportunity: the timing evidence still needs to
  place Dr. Elias Thorne near Lord Finch during the critical window.
  The clue pointing toward Dr. Elias Thorne (half-empty bottle of
  Chloral Hydrate) may be circumstantial or misleading.
  Your strongest evidence so far is: small ornate silver locket, faint
  sweet almond-like scent lingering.
  Type CASE or SUSPECTS to review the reasoning, then accuse the suspect
  with the strongest means, motive, and opportunity chain.
```

### Final accusation
```
  > accuse eleanor vance
  ...
  You lay out the evidence piece by piece until Eleanor Vance has
  nowhere left to hide. The final reconstruction is now clear.

================================================================
CASE SOLVED
================================================================

    You've done it. Eleanor Vance is under arrest.

    THE TRUTH:
    Eleanor Vance harbored a deep-seated vendetta against Lord Alistair
  Finch. Years ago, Finch's ruthless business tactics had deliberately
  ruined her family's esteemed publishing house, driving her father to
  despair and ultimately suicide. Eleanor, then a young girl, vowed
  revenge. She meticulously planned her infiltration into Blackwood
  Manor as the librarian, patiently waiting for her opportunity. On the
  night of the murder, she seized the moment during a brief power
  flicker, knowing it would provide the perfect cover. Slipping into
  Finch's study, she quickly administered a potent Belladonna extract
  into his brandy, a poison she had researched extensively. She then
  returned to the library, feigning work on new acquisitions, confident
  her alibi would hold, unaware she had left a trail of subtle clues.
```

---

## Requirements

- Python 3.10 or newer recommended
- A Gemini API key set in the `GEMINI_API_KEY` environment variable
- Python package listed in `requirements.txt`:

```text
google-genai>=0.8.0
```

---

## API key setup

The code reads the Gemini key from an environment variable in `config.py`:

```python
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
```

Set the key before running the game.

### macOS / Linux

```bash
export GEMINI_API_KEY="your_api_key_here"
```

### Windows PowerShell

```powershell
$env:GEMINI_API_KEY="your_api_key_here"
```

### Windows Command Prompt

```cmd
set GEMINI_API_KEY=your_api_key_here
```

If the key is missing, the system may still load some local files, but live story generation, LLM action interpretation, LLM room generation, LLM drama-manager repairs, and LLM response generation will fail when they are needed.

---

## Installation

From the project root directory:

```bash
python -m venv .venv
source .venv/bin/activate      # macOS/Linux
# .venv\Scripts\activate       # Windows PowerShell/CMD

pip install -r requirements.txt
```

---

## How to run the system

Run all commands from the project root directory, the folder that contains `game.py`.

### Option A: Run with the included pre-generated crime state

This is the most reproducible way to run the submitted system:

```bash
python game.py --crime-state output/generated_crime_state_20260502_110643.json --debug --save-log
```

This command:

- loads the included crime state,
- builds the game world,
- starts the interactive mystery,
- shows drama-manager/action-classification information because of `--debug`, and
- saves a game log to `output/` because of `--save-log`.

### Option B: Generate a fresh crime state and play it

```bash
python game.py --theme "locked observatory murder" --debug --save-log
```

You can replace the theme with any short seed phrase, such as:

```bash
python game.py --theme "poisoning at a research lab" --debug --save-log
```

When a new crime state is generated, it is saved in `output/` by default as:

```text
output/generated_crime_state_YYYYMMDD_HHMMSS.json
```

### Option C: Generate a fresh crime state without saving it

```bash
python game.py --theme "murder at a private archive" --no-save-crime-state
```

This is useful for quick experiments, but it is less useful for grading or debugging because the exact generated case will not be saved.

---

## Command-line flags

```text
--crime-state PATH       Load an existing crime-state JSON file instead of generating a new one.
--theme TEXT             Optional seed theme for generating a new crime state.
--no-save-crime-state    Do not save newly generated crime-state JSON.
--debug                  Print action classifications, DM logs, and state summaries.
--save-log               Save a JSON game log in output/.
```

Recommended grading command:

```bash
python game.py --crime-state output/generated_crime_state_20260502_110643.json --debug --save-log
```

---

## Typical play flow

A typical successful playthrough looks like this:

1. Start at the entrance.
2. Use `look`, `map`, and movement commands to explore rooms.
3. Use `search room` and `examine <object>` to find evidence.
4. Use `talk to <suspect>` to gather alibis and witness statements.
5. Use `case`, `evidence`, and `suspects` to review progress.
6. Find at least the configured minimum number of clues.
7. Interview the strongest suspect if needed.
8. Use `accuse <suspect>` when enough evidence has been collected.

The game prevents immediate shortcutting to the solution. `config.py` currently requires at least three discovered clues before a successful accusation is possible:

```python
MIN_CLUES_TO_ACCUSE = 3
```

---

## Debug mode and drama-manager visibility

Use `--debug` when demonstrating or grading the system:

```bash
python game.py --crime-state output/generated_crime_state_20260502_110643.json --debug
```

Debug mode prints information such as:

```text
[ACTION] verb='examine' target='residue' category=constituent | ...
[DM] DM ACCOMMODATE ...
[Turn 4 | Clues: 2/5 | Interviews: 1/4 | Plot points: 3/10 | Location: ...]
```

This is the easiest way to see what the drama manager is doing behind the scenes. It also makes it clear when a player action is classified as constituent, consistent, or exceptional.

---

## Runtime and cost

Runtime depends on whether a crime state is generated from scratch and how many open-ended commands require LLM calls.

Typical local runtime:

- Loading the included crime state: usually under 1 minute to start, depending on room-generation LLM latency.
- Generating a new crime state: usually 1-3 minutes, depending on Gemini API latency and retry behavior.
- Playing the game: response time is usually a few seconds per command when an LLM call is needed; deterministic commands are faster.

API usage:

- The only external paid/free-tier API used by this code is Gemini through `google-genai`.
- The configured model names are in `config.py`; all major tasks currently use `gemini-2.5-flash` by default.
- Cost depends on the Gemini account, model pricing, prompt sizes, and number of turns.
- The included crime-state run is cheaper than generating a new crime state because it skips the Phase I generation call.

To reduce cost while testing:

```bash
python game.py --crime-state output/generated_crime_state_20260502_110643.json
```

Use short commands and the deterministic commands listed above when possible.

---

## Project architecture

![alt text](https://github.com/mulan-liu08/sly-fox/blob/main/phase_2_architecture_diagram.png "architecture diagram")

### Main files

| File | Purpose |
| --- | --- |
| `game.py` | Parses CLI flags, loads or generates the crime state, builds the world, runs the interactive loop, logs turns, and ends the game. |
| `config.py` | Stores model names, temperatures, limits, clue thresholds, output directory, and API-key lookup. |
| `llm_client.py` | Wraps Gemini calls, handles retries, and extracts JSON from model responses. |
| `phase1_generator.py` | Generates the hidden murder mystery state: setting, victim, culprit, suspects, clues, timeline, and backstory. |
| `world/game_state.py` | Defines the core data structures: `Room`, `GameObject`, `NPC`, `PlotPoint`, `CausalLink`, `Player`, and `GameState`. |
| `world/world_generator.py` | Converts the crime-state JSON into playable rooms, evidence objects, NPCs, plot points, and causal links. |
| `engine/action_interpreter.py` | Converts player text into an `InterpretedAction` and classifies it as constituent, consistent, or exceptional. |
| `engine/action_executor.py` | Applies actions to the game state: movement, search, examine, take/drop, talk, show, accuse, help, map, evidence, and hints. |
| `engine/response_generator.py` | Converts execution results and DM decisions into readable second-person game narration. |
| `drama_manager/drama_manager.py` | Handles intervention and accommodation, including blocking dangerous actions, repairing threatened evidence, giving hints, and causing plot-relevant events. |

### Architecture to Code Mapping
- Crime Story Generation: `phase1_generator.py` → `generate_crime_world_state()`
- World Generator: `world/world_generator.py` → `build_game_world()`
- Game World State: `world/game_state.py` → `GameState`, `Room`, `NPC`, `PlotPoint`, `CausalLink`
- Action Interpreter (LLM): `engine/action_interpreter.py` → `interpret_action()`
- Action Classifier: `engine/action_interpreter.py` → `InterpretedAction.category`
- Drama Manager: `drama_manager/drama_manager.py` → `DramaManager.evaluate()`
- Accommodation: `drama_manager/drama_manager.py` → `_accommodate()`, `_generate_repair()`
- Response Generator (LLM): `engine/response_generator.py` → `generate_response()`
- Main Game Loop: `game.py` → `run_game()`
