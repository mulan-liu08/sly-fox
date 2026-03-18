# 🦊 Sly Fox — AI Crime Mystery Generator

**Team:** Sly Fox — Samreen Farooqui · Mulan Liu · Keegan Thompson  
**Course:** CS7634 AI Storytelling  
**Template:** Template 1 — Suspense Generation  

---

## Overview

This system generates complete, suspenseful murder mystery stories using a
three-phase pipeline:

```
Phase 1 ── Crime World State Generation  (Gemini LLM)
Phase 2 ── Iterative Suspense Loop       (MetaController + Gemini + Consistency Checker)
Phase 3 ── Story Assembly                (Gemini LLM — fluent narration + revelation)
```

The key design principle: **the crime world state is generated first as an
immutable ground truth, then the investigation story references but never
contradicts it.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│ Phase 1: Crime Generation                                           │
│                                                                     │
│  crime_generator.py ──► Crime World State (JSON)                    │
│     LLM creates: victim, culprit (MMO+method), 4+ suspects,         │
│     7+ clues (5 real + 1-2 red herrings), timeline, backstory       │
│                                                                     │
│  validators.py ──► 3-Phase Validation (non-LLM)                     │
│     Phase 1: Structure   Phase 2: Complexity   Phase 3: Consistency │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ Crime World State
┌────────────────────────────────▼────────────────────────────────────┐
│ Phase 2: Iterative Suspense Loop (meta_controller.py)               │
│                                                                     │
│  ┌──────────────────┐  prompt  ┌──────────────────────────────────┐ │
│  │  MetaController  │─────────►│  LLM Story Generation            │ │
│  │  (arc navigator) │          │  Detective Action →              │ │
│  └──────────────────┘          │  Obstacle Blocks →               │ │
│          ▲                     │  Stakes Escalate                 │ │
│          │ valid               └──────────────┬───────────────────┘ │
│  ┌───────┴──────────┐   proposed              │                     │
│  │ Plot Point       │◄────────────────────────┘                     │
│  │ Accumulator      │                                               │
│  │ (15+ validated)  │          ┌──────────────────────────────────┐ │
│  └──────────────────┘          │  ConsistencyChecker (non-LLM)   │ │
│                                │  • Secret masking (logic gate)  │ │
│                                │  • Contradiction detection      │ │
│                                │  • Anti-repetition buffer       │ │
│                                │  • Rationality filter           │ │
│                                └──────────────────────────────────┘ │
│  Iterate until 15+ plot points, suspense peaks                      │
└────────────────────────────────┬────────────────────────────────────┘
                                 │ 15+ Plot Points
┌────────────────────────────────▼────────────────────────────────────┐
│ Phase 3: Final Story Assembly (story_assembler.py)                  │
│                                                                     │
│  FluentNarrator ──► Expands raw plot points into polished prose     │
│  RevelationWriter ──► Generates detective's final explanation       │
│                                                                     │
│  Output: Complete suspenseful mystery (.md file)                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Setup

### 1. Clone / unzip the project

```bash
cd your-workspace
# (unzip or copy the sly_fox_mystery folder here)
cd sly_fox_mystery
```

### 2. Create a virtual environment (recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate        # Mac/Linux
.venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get a Gemini API key

1. Go to https://aistudio.google.com/app/apikey
2. Create a key (free tier works fine for development)
3. Export it:

```bash
export GEMINI_API_KEY="your-key-here"   # Mac/Linux
set GEMINI_API_KEY=your-key-here        # Windows CMD
$env:GEMINI_API_KEY="your-key-here"     # PowerShell
```

Or edit `config.py` directly and paste your key into `GEMINI_API_KEY`.

---

## Running

### Basic run

```bash
python main.py
```

Generates a complete mystery and saves it to `output/mystery_<timestamp>.md`.

### With a theme seed

```bash
python main.py --theme "tech startup"
python main.py --theme "Victorian art museum"
python main.py --theme "cruise ship"
```

### Save the crime world state (for debugging / reuse)

```bash
python main.py --save-state
```

This also writes `output/crime_state_<timestamp>.json`.

### Reuse a saved crime world state (skip Phase 1)

```bash
python main.py --load-state output/crime_state_20241015_143201.json
```

Useful when debugging Phase 2 or 3 — you don't have to regenerate the crime each time.

### Custom output path

```bash
python main.py --output my_story.md
```

---

## Running Tests (no API key needed)

All non-LLM components have unit tests:

```bash
python tests/test_components.py
```

Expected output: **9 passed, 0 failed**

These tests cover:
- `validators.py` — all 3 validation phases
- `consistency_checker.py` — SecretTracker, EventMemoryBuffer, ConsistencyChecker
- No Gemini API calls required

---

## File Structure

```
sly_fox_mystery/
├── config.py              # API key, model names, story parameters
├── llm_client.py          # Thin Gemini API wrapper (retry, JSON extraction)
├── crime_generator.py     # Phase 1: crime world state generation
├── validators.py          # 3-phase non-LLM validation
├── consistency_checker.py # Non-LLM plot point gate (secret masking, anti-repetition)
├── meta_controller.py     # Phase 2: iterative suspense loop
├── story_assembler.py     # Phase 3: fluent narration + revelation scene
├── main.py                # Orchestrator / CLI entry point
├── requirements.txt
├── output/                # Generated stories and crime states saved here
└── tests/
    └── test_components.py # Unit tests (no API key needed)
```

---

## Design Decisions

### Why pre-generate the crime world state?

The rubric asks how we handle pre-generation. Our answer: generate **all** crime
facts in Phase 1 (culprit, motive, method, clues, red herrings, alibis) and
treat them as **immutable constraints**. The LLM in Phase 2 never sees the
culprit's name until step 13+ of 18 — the `SecretTracker` in
`consistency_checker.py` enforces this with logic masking.

### How do we ensure non-triviality?

Three layers:

1. **Structure**: ≥4 suspects each missing exactly one MMO element. ≥5 clues with
   1-2 red herrings per 5. At least 2 chained clues (prerequisite system).
2. **Validation**: `validators.py` checks all counts and ratios before Phase 2 starts.
   If the LLM generates a trivial crime state, it's rejected and regenerated.
3. **Plot arc**: The MetaController's `_arc_instruction()` enforces
   ESTABLISH → ESCALATE → PIVOT → CLIMAX → RESOLVE, spreading revelations across
   the full 18-step arc.

### How do we prevent LLM hallucination?

- The crime world state JSON is injected into **every** Phase 2 prompt as ground truth.
- The `ConsistencyChecker` runs **after** each LLM output and blocks contradictions
  before they enter the accumulator.
- Failed plot points are retried with the rejection reason in the prompt, nudging
  the LLM away from the violation.

## Template-Specific Questions

**Q: If you pre-generate crime details, how do you adapt the technique?**

A: We generate ALL details in Phase 1 and store them in a JSON "Crime World State".
We then strategically reveal details to the LLM through the 18 prompts in Phase 2,
ordered for suspense rather than generation order. The LLM controls detective
emotions/reasoning/dialogue; we control facts. The SecretTracker class assigns
each secret a minimum step number before it may appear.

**Q: 3-phase validation?**
- Phase 1 (Structure): No orphaned clues, red herrings have explanations, prerequisite IDs exist.
- Phase 2 (Complexity): ≥5 clues, 1-2 RH per 5, ≥2 chained, ≥4 suspects, each missing one MMO.
- Phase 3 (Consistency): Culprit has all 3 MMO, innocent suspects each lack one, no duplicate IDs, victim named.

## Example Output Structure

```
# The Hargrove Manor Murder
*A crime mystery — October 14, 1987*

---

[Narrated investigation — ~15-18 paragraphs covering all plot points]


[Detective's climactic explanation tying every clue back to the truth]

---
*End of story. Detective: Morgan Reyes | Victim: ... | Setting: ...*
```
