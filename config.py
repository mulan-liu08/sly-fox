import os

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

GEMINI_FLASH = "gemini-2.5-flash"
GEMINI_PRO   = "gemini-2.5-pro"

ACTION_MODEL   = GEMINI_FLASH   
RESPONSE_MODEL = GEMINI_FLASH   
REPAIR_MODEL   = GEMINI_FLASH   
WORLD_MODEL    = GEMINI_FLASH   
CRIME_GEN_MODEL = GEMINI_FLASH   

MAX_INPUT_WORDS      = 10    
MIN_CLUES_TO_ACCUSE  = 3     
HINT_AFTER_N_STUCK   = 4     
MAX_REPAIR_ATTEMPTS  = 3     
MAX_CRIME_GEN_ATTEMPTS = 3    
MIN_SUSPECTS = 3              
MIN_CLUES = 5                 

ACTION_TEMP   = 0.1   
RESPONSE_TEMP = 0.85  
REPAIR_TEMP   = 0.4   
CRIME_GEN_TEMP = 0.2  

OUTPUT_DIR   = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
