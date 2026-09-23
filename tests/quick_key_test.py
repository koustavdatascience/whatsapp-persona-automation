"""
tests/quick_key_test.py
------------------------
Quick smoke test — confirms the Gemini API key in .env is valid and
the model is reachable. Run this any time you suspect the key has
expired or the API is down.

Usage:
    python3 tests/quick_key_test.py
"""

import os
import sys
from dotenv import load_dotenv
from google import genai

load_dotenv()

key = os.getenv("GEMINI_API_KEY", "")

if not key:
    print("❌  GEMINI_API_KEY is not set in .env")
    sys.exit(1)

print(f"🔑  Key found: {key[:8]}{'*' * (len(key) - 8)}")
print("📡  Sending test prompt to gemini-3.6-flash...")

try:
    client = genai.Client(api_key=key)
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents="Reply with exactly one word: alive",
    )
    reply = response.text.strip()
    print(f"✅  Gemini responded: \"{reply}\"")
    print("    API key is valid and model is reachable.")
except Exception as e:
    print(f"❌  Gemini API error: {e}")
    print("    Regenerate the key at https://aistudio.google.com/app/apikey")
    sys.exit(1)
