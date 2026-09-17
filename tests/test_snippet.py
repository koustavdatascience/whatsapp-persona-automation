import json
import os
import sys
import time
from google import genai
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT_DIR)

load_dotenv(os.path.join(ROOT_DIR, ".env"))

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

persona_path = os.path.join(ROOT_DIR, "persona", "persona.json")
with open(persona_path, "r", encoding="utf-8") as f:
    persona = json.load(f)

test_prompts = [
    ("gf", "I am going to be late today, can you pick me up?i"),
    ("roshun", "kokhon debo bolish"),
    ("gaming", "kothae re"),
    ("professional", "I have a new video ready when can we connect?"),
]

for relationship, incoming in test_prompts:
    rel_data = persona["relationships"][relationship]
    tone = rel_data["tone"]
    examples = rel_data["example_replies"]
    hinglish_ratio = rel_data.get("hinglish_ratio", persona["hinglish_ratio"])
    language_rule = rel_data.get("language", "English")

    prompt = f"""You are texting as: {persona['identity']}
Relationship: {relationship}
Tone: {tone}
Language Constraints: {language_rule}
Hinglish/Bengali ratio to match for this relationship: {hinglish_ratio}
Example replies in this tone: {examples}
Incoming message: "{incoming}"
Reply in character, one short WhatsApp-style message only."""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model="gemini-3.6-flash", contents=prompt
            )
            print(f"[{relationship}] {incoming} -> {response.text.strip()}")
            break
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
                time.sleep(15)
            else:
                time.sleep(3)
            if attempt == 2:
                print(f"[{relationship}] Failed: {e}")
    time.sleep(3)
