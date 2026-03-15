"""
config.py — Central configuration for Sly Fox Crime Mystery Generator
Team: Sly Fox (Samreen Farooqui, Mulan Liu, Keegan Thompson)
Course: CS7634 AI Storytelling
"""

import os
from dotenv import load_dotenv

load_dotenv(override=True)

# ─── Gemini API ───────────────────────────────────────────────────────────────
# Set your key here OR export GEMINI_API_KEY=... in your shell before running.
GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

# Model choices (swap between flash and pro here)
GEMINI_FLASH   = "gemini-2.5-flash"   # faster / cheaper
GEMINI_PRO     = "gemini-2.5-pro"     # higher quality

# Which model to use for each phase (change to GEMINI_PRO for better quality)
CRIME_GEN_MODEL    = GEMINI_FLASH   # Phase 1: crime world state generation
PLOT_GEN_MODEL     = GEMINI_FLASH   # Phase 2: iterative suspense loop
NARRATOR_MODEL     = GEMINI_PRO   # Phase 3: fluent narration (swap to GEMINI_PRO for final demo)

# ─── Temperature settings ────────────────────────────────────────────────────
# Low temp for structured JSON output (schema adherence is critical).
# High temp for creative prose (variety and surprise matter more than precision).
JSON_TEMPERATURE  = 0.2   # Phase 1 crime world state, any expect_json=True call
PROSE_TEMPERATURE = 0.9   # Phase 2 plot points, Phase 3 narration

# ─── Story parameters ─────────────────────────────────────────────────────────
MIN_PLOT_POINTS    = 15      # Required minimum
TARGET_PLOT_POINTS = 18      # We aim slightly higher for buffer
MIN_SUSPECTS       = 4
MIN_CLUES          = 5
RED_HERRING_RATIO  = (1, 2)  # 1–2 red herrings per 5 clues
MAX_REGEN_ATTEMPTS = 3       # How many times to retry a failed plot point

# ─── Output ───────────────────────────────────────────────────────────────────
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
