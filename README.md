# Sly Fox — Interactive Mystery

**Team name:** Sly Fox  
**System name:** Sly Fox — Interactive Mystery  
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

## Requirements

- Python 3.10 or newer recommended
- A Gemini API key set in the `GEMINI_API_KEY` environment variable
- Python package listed in `requirements.txt`:

```text
google-genai>=0.8.0
```

Optional for tests:

```text
pytest
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

For running the test suite:

```bash
pip install pytest
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

```text
                    +----------------------+
                    |      game.py         |
                    | CLI + main game loop |
                    +----------+-----------+
                               |
                               v
+-------------------+   +----------------------+   +----------------------+
| phase1_generator.py|  | world/world_generator.py | | world/game_state.py  |
| Crime-state JSON   |->| Rooms, NPCs, objects, |->| Dataclasses + global |
| generation         |  | plot points, links    |  | mutable game state   |
+-------------------+   +----------------------+   +----------+-----------+
                                                              |
                                                              v
+----------------------+   +----------------------+   +----------------------+
| engine/action_       |   | engine/action_       |   | drama_manager/       |
| interpreter.py       |-->| executor.py          |-->| drama_manager.py     |
| Command parsing +    |   | Applies actions to   |   | Detects exceptions, |
| classification       |   | GameState            |   | hints, accommodation|
+----------------------+   +----------+-----------+   +----------+-----------+
                                      |                          |
                                      v                          v
                              +----------------------+   +----------------------+
                              | engine/response_    |   | llm_client.py        |
                              | generator.py        |   | Gemini wrapper +    |
                              | Player-facing text  |   | JSON extraction     |
                              +----------------------+   +----------------------+
```

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
| `tests/test_p2_components.py` | Unit tests for movement, clue discovery, unlocking dependent clues, inventory, accusations, solvability, NPC interviews, and world-generation helpers. |

---

## How the Intervention and Accommodation template is implemented

### 1. Constituent, consistent, and exceptional actions

The action categories are defined in `world/game_state.py`:

```python
class ActionCategory(Enum):
    CONSTITUENT  = "constituent"
    CONSISTENT   = "consistent"
    EXCEPTIONAL  = "exceptional"
```

The action interpreter in `engine/action_interpreter.py` uses deterministic parsing for common commands and falls back to Gemini for open-ended commands. It builds a context containing the current room, visible objects, visible NPCs, inventory, available plot points, active causal links, and discovered clues. The LLM prompt asks for a normalized verb, target, category, reasoning, affected causal links, and plot-point ID.

### 2. Causal links and solvability

`world/world_generator.py` builds causal links between prerequisite clues and dependent clues, and between real clues and the final accusation. The game state tracks these links in `GameState.causal_links`.

`GameState.is_solvable()` checks whether enough evidence still exists to make the mystery solvable. If critical evidence is destroyed or removed so that fewer than the required number of clues remain discoverable, the investigation fails.

### 3. Exception handling

The drama manager receives interpreted actions from the main loop in `game.py`. If an action is exceptional, `DramaManager._handle_exception()` checks what evidence or causal links are threatened.

Possible outcomes:

- **Block:** The action is prevented because it would make the case impossible or is inappropriate for the detective role.
- **Accommodate:** The drama manager allows the action but repairs the story by relocating or re-sourcing the threatened clue.
- **Fail later:** If the game state becomes unsolvable, the game prints the failed-investigation ending.

### 4. Accommodation

Accommodation happens in `drama_manager/drama_manager.py`:

- `_generate_repair()` asks Gemini to propose a feasible story repair for threatened evidence.
- `_apply_repair()` applies the repair to the game state, usually by moving damaged evidence to a new room or adding the relevant information to an NPC.
- The repair is recorded in `GameState.accommodations_made` and appears in debug logs.

### 5. Hints and causers

The drama manager also helps preserve story flow:

- If the player performs too many non-progress actions, `_give_hint()` points them toward an available plot point.
- `_check_for_causer()` can cause a plot-relevant event to surface when the player needs momentum.

These features make the story more robust without forcing every player action into a menu of predefined choices.

---

## Game-state data model

The most important data structures are in `world/game_state.py`.

### `GameState`

Stores the full mutable world:

- `rooms`: all locations and exits
- `objects`: evidence and ordinary objects
- `npcs`: suspects and witnesses
- `player`: location, inventory, discovered clues, interviews, notes, accusation state
- `plot_points`: events required or useful for story progress
- `causal_links`: conditions that must remain true for story solvability
- `crime_state`: hidden Phase I generated story facts
- `executed_plot_points`: completed plot events
- `broken_causal_links`: threatened or broken causal conditions
- `accommodations_made`: drama-manager repairs
- `action_log`: turn-level history

### `PlotPoint`

Represents story progress requirements. Examples include:

- arriving at the scene,
- discovering each clue,
- interviewing suspects,
- revealing the culprit.

### `CausalLink`

Represents a condition that must remain intact. Example:

```text
clue_01 must remain accessible so clue_03 can become discoverable.
```

### `GameObject`

Represents evidence and interactable objects. Evidence objects have:

```python
is_evidence=True
clue_id="clue_XX"
```

### `NPC`

Represents suspects and witnesses. NPCs can store:

- alibis,
- known facts,
- locked facts revealed by evidence,
- culprit status,
- cleared/suspicious status.

---

## Important configuration values

Edit `config.py` to change the behavior of the system.

```python
GEMINI_FLASH = "gemini-2.5-flash"
GEMINI_PRO   = "gemini-2.5-pro"

ACTION_MODEL    = GEMINI_FLASH
RESPONSE_MODEL  = GEMINI_FLASH
REPAIR_MODEL    = GEMINI_FLASH
WORLD_MODEL     = GEMINI_FLASH
CRIME_GEN_MODEL = GEMINI_FLASH

MAX_INPUT_WORDS        = 10
MIN_CLUES_TO_ACCUSE    = 3
HINT_AFTER_N_STUCK     = 4
MAX_REPAIR_ATTEMPTS    = 3
MAX_CRIME_GEN_ATTEMPTS = 3
MIN_SUSPECTS           = 3
MIN_CLUES              = 5
```

Useful values to adjust during testing:

- `MIN_CLUES_TO_ACCUSE`: lower it for very short debugging runs.
- `HINT_AFTER_N_STUCK`: lower it to make hints appear sooner.
- `MAX_REPAIR_ATTEMPTS`: increase it if accommodation often fails.
- Model constants: change these to use a different Gemini model.

---

## Running tests

Install test dependencies:

```bash
pip install -r requirements.txt
pip install pytest
```

Then run:

```bash
python -m pytest -q
```

The tests use a stub API key and mostly exercise deterministic components, including:

- valid and invalid movement,
- clue discovery,
- dependent clue unlocking,
- taking inventory objects,
- too-early accusation blocking,
- correct and incorrect accusations,
- plot-point unlocking,
- solvability checks,
- NPC interviews,
- helper functions for room and clue generation.

If `pytest` reports `ModuleNotFoundError: No module named 'google'`, install the required Gemini package:

```bash
pip install -r requirements.txt
```

---

## Output files

The system writes generated crime states and optional logs to `output/`.

Examples:

```text
output/generated_crime_state_20260502_110643.json
output/game_log_YYYYMMDD_HHMMSS.json
```

A saved game log includes:

- crime-state summary,
- turn inputs,
- interpreted verbs,
- action categories,
- drama-manager actions,
- response previews,
- final clue and win/loss state,
- accommodation records.

Use `--save-log` when demonstrating the drama manager.

---

## Suggested successful demonstration path

Because generated worlds vary, exact room names and clue names may differ. Use the built-in guidance commands to adapt during a run.

Suggested demonstration flow:

```text
look
map
search room
examine <visible evidence object>
talk to <visible suspect>
evidence
suspects
hint
move <direction from exits>
search room
examine <new evidence object>
case
accuse <strongest suspect after enough clues>
```

When enough clues are found, the game prints guidance like:

```text
Clues found: 3 | Enough evidence to accuse
```

Then use:

```text
case
suspects
accuse <suspect name>
```

---

## Suggested exceptional-action demonstration

Run with debug mode:

```bash
python game.py --crime-state output/generated_crime_state_20260502_110643.json --debug --save-log
```

Then try an action that threatens evidence or an NPC, such as:

```text
destroy <evidence object>
kill <suspect name>
remove <evidence object>
```

Expected drama-manager behavior:

- The action interpreter classifies the command as `exceptional` if it threatens evidence, a witness, or a causal link.
- The drama manager logs the threat.
- The drama manager either blocks the action or attempts accommodation.
- If accommodation succeeds, the debug output logs `DM ACCOMMODATE` and records the repair.
- If the action must be blocked, the player receives an in-world message explaining why the detective cannot proceed that way.

---

## Troubleshooting

### `Error: failed to generate a crime state`

Most likely causes:

- `GEMINI_API_KEY` is not set.
- The Gemini API request failed or exceeded quota.
- The model returned JSON that did not pass validation after all retry attempts.

Try:

```bash
export GEMINI_API_KEY="your_api_key_here"
python game.py --crime-state output/generated_crime_state_20260502_110643.json --debug
```

### `ModuleNotFoundError: No module named 'google'`

Install dependencies:

```bash
pip install -r requirements.txt
```

### The game says it cannot find a target

Try one of:

```text
look
search room
map
exits
inventory
evidence
suspects
hint
```

The object or NPC must usually be in the current room or inventory.

### Accusation fails even with a suspect name

The game requires enough evidence before accusation. Use:

```text
evidence
case
suspects
hint
```

Then continue investigating until the game says you have enough evidence to accuse.

---

## Notes for graders

Recommended command:

```bash
python game.py --crime-state output/generated_crime_state_20260502_110643.json --debug --save-log
```

The `--debug` flag is important because many drama-manager actions modify hidden state. The debug log exposes action categories and drama-manager intervention/accommodation decisions.

The code is organized so that the architecture diagram above maps directly to the files in the repository. The most important representative implementation files are:

- `world/game_state.py` for world-state representation,
- `world/world_generator.py` for story-to-game conversion,
- `engine/action_interpreter.py` for open-ended command classification,
- `engine/action_executor.py` for game-rule execution,
- `drama_manager/drama_manager.py` for intervention and accommodation,
- `engine/response_generator.py` for player-facing narration,
- `game.py` for the playable loop.

