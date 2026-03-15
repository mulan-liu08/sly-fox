import os
from google import genai
from dotenv import load_dotenv

load_dotenv(override=True)

try:
    gemini_key = os.environ['GEMINI_API_KEY']
    print("API Keys successfully loaded from environment variables.")
except KeyError as e:
    print(f"ERROR: Environment variable {e} not set. Please set it using 'export' or 'setx'.")
    exit()

try:
    gemini_client = genai.Client(api_key=gemini_key)
    response = gemini_client.models.generate_content(
        # model="gemini-3.1-pro-preview",
        # model="gemini-3-flash-preview",
        # model="gemini-2.5-flash",
        model="gemini-2.5-pro",
        contents="Say 'ready'"
    )
    print(f"Gemini Pro Test Success! Model responded: {response.text.strip()[:50]}...")
except Exception as e:
    print(f"Gemini Pro Test FAILED: {e}")
