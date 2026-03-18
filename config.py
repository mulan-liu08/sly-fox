import os
from dotenv import load_dotenv

load_dotenv(override=True)

GEMINI_API_KEY = os.environ['GEMINI_API_KEY']

GEMINI_FLASH   = "gemini-2.5-flash"
GEMINI_PRO     = "gemini-2.5-pro"

CRIME_GEN_MODEL    = GEMINI_FLASH   # Phase 1: crime world state generation
PLOT_GEN_MODEL     = GEMINI_FLASH   # Phase 2: iterative suspense loop
NARRATOR_MODEL     = GEMINI_PRO   # Phase 3: fluent narration

JSON_TEMPERATURE  = 0.2   # Phase 1 crime world state, any expect_json=True call
PROSE_TEMPERATURE = 0.9   # Phase 2 plot points, Phase 3 narration

MIN_PLOT_POINTS    = 15      
TARGET_PLOT_POINTS = 18      
MIN_SUSPECTS       = 4
MIN_CLUES          = 5
RED_HERRING_RATIO  = (1, 2)  # 1–2 red herrings per 5 clues
MAX_REGEN_ATTEMPTS = 3       # How many times to retry a failed plot point

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
