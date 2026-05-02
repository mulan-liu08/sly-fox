"""
config.py — Phase 2 configuration for Sly Fox Interactive Mystery
Team: Sly Fox (Samreen Farooqui, Mulan Liu, Keegan Thompson)
Course: CS7634 AI Storytelling — Phase 2
Template: Intervention and Accommodation
"""

import os

# ─── Gemini API ───────────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")

GEMINI_FLASH = "gemini-2.5-flash"
GEMINI_PRO   = "gemini-2.5-pro"

# Model assignments
ACTION_MODEL   = GEMINI_FLASH   # Interprets player's free-text input
RESPONSE_MODEL = GEMINI_FLASH   # Generates atmospheric prose response
REPAIR_MODEL   = GEMINI_FLASH   # Drama manager story repair
WORLD_MODEL    = GEMINI_FLASH   # World generation from crime state
CRIME_GEN_MODEL = GEMINI_FLASH   # Optional Phase 1 crime-state generation

# ─── Game parameters ─────────────────────────────────────────────────────────
MAX_INPUT_WORDS      = 10    # Soft cap on player input (warn if exceeded)
MIN_CLUES_TO_ACCUSE  = 3     # Player must find this many clues before accusing
HINT_AFTER_N_STUCK   = 4     # DM gives hint after N consecutive non-constituent actions
MAX_REPAIR_ATTEMPTS  = 3     # Times accommodation tries to repair a broken causal link
MAX_CRIME_GEN_ATTEMPTS = 3    # Attempts for optional Phase 1 crime-state generation
MIN_SUSPECTS = 3              # Phase 1 generation requirement
MIN_CLUES = 5                 # Phase 1 generation requirement

# ─── Temperatures ────────────────────────────────────────────────────────────
ACTION_TEMP   = 0.1   # Low — classification needs to be deterministic
RESPONSE_TEMP = 0.85  # High — prose should be atmospheric and varied
REPAIR_TEMP   = 0.4   # Medium — repair needs creativity but also coherence
CRIME_GEN_TEMP = 0.2   # Low/medium — crime-state generation needs consistency

# ─── Paths ───────────────────────────────────────────────────────────────────
OUTPUT_DIR   = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
