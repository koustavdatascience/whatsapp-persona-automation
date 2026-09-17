import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google import genai
from dotenv import load_dotenv
from persona.persona_loader import PersonaManager

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
manager = PersonaManager()

test_cases = [
    {
        "tier": "partner",
        "incoming": "Good morning, kothay achis?",
    },
    {
        "tier": "friends",
        "incoming": "Valorant khelbi akhon? 5 mins e lobby bana",
    },
    {
        "tier": "professional",
        "incoming": "Hey Koustav, can you share an update on the video draft?",
    },
    {
        "tier": "unknown",
        "incoming": "Hi Koustav, got your number from the group.",
    },
]

print("==================================================")
print("🤖 TESTING RELATIONSHIP PERSONA REPLIES (GEMINI)")
print("==================================================\n")

for test in test_cases:
    tier = test["tier"]
    incoming = test["incoming"]

    system_prompt = manager.build_system_prompt(tier)
    full_prompt = f"{system_prompt}\n\nIncoming Message: \"{incoming}\""

    response = client.models.generate_content(
        model="gemini-3.6-flash", contents=full_prompt
    )

    print(f"📌 Relationship Tier : {tier.upper()}")
    print(f"📩 Incoming Message  : {incoming}")
    print(f"🤖 Generated Reply  : {response.text.strip()}")
    print("-" * 50 + "\n")
