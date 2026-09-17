import json
import os


class PersonaManager:
    """Manages relationship-specific personas from consolidated per-chat style_signals.json files."""

    def __init__(self, base_dir="persona"):
        self.base_dir = base_dir
        self.personas = {}
        self.load_all_personas()

    def load_all_personas(self):
        """Loads persona configurations from per-chat folders."""
        tiers = ["gf", "client", "roshun", "valorant", "unknown"]
        for tier in tiers:
            file_path = os.path.join(self.base_dir, tier, "style_signals.json")
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    self.personas[tier] = json.load(f)

        # Mappings & Aliases
        if "gf" in self.personas:
            self.personas["partner"] = self.personas["gf"]
        if "valorant" in self.personas:
            self.personas["friends"] = self.personas["valorant"]
            self.personas["gaming"] = self.personas["valorant"]
        if "client" in self.personas:
            self.personas["professional"] = self.personas["client"]

    def get_persona(self, tier: str) -> dict:
        """Retrieves a persona dictionary by relationship tier name."""
        return self.personas.get(tier.lower(), self.personas.get("unknown"))

    def build_system_prompt(
        self, tier: str, retrieved_history: list = None
    ) -> str:
        """Generates a complete System Prompt for LLM generation matching the relationship tier."""
        persona = self.get_persona(tier)
        style = persona.get("style_rules", {})
        safety = persona.get("safety_rules", [])
        examples = persona.get("few_shot_examples", [])

        prompt = f"""You are Koustav replying to an incoming WhatsApp message.
Relationship Tier: {persona.get('name', tier).upper()}

[STYLE GUIDELINES]
- Target Message Length: {style.get('avg_length', 'Concise')}
- Casing & Formatting: {style.get('casing', 'Casual')}
- Language & Vocabulary: {style.get('language', 'English')}
- Hinglish/Bengali Ratio: {persona.get('hinglish_ratio', '0.0%')}
- Emoji Usage: {style.get('emoji_usage', 'Subtle')}
- Tone: {style.get('tone', 'Natural')}

[SAFETY & BOUNDARY RULES]
"""
        for rule in safety:
            prompt += f"- {rule}\n"

        prompt += "\n[FEW-SHOT TIER EXAMPLES]\n"
        for ex in examples:
            prompt += f"Incoming: \"{ex['incoming']}\"\nYour Reply: \"{ex['response']}\"\n\n"

        if retrieved_history:
            prompt += "[RETRIEVED PAST CHAT EXAMPLES (HISTORY BRAIN - RAG)]\n"
            for item in retrieved_history:
                prompt += f"Past Incoming: \"{item.get('incoming')}\"\nYour Past Reply: \"{item.get('response')}\"\n\n"

        prompt += (
            "Now write a natural, authentic reply for Koustav. Output ONLY"
            " the reply text."
        )
        return prompt


if __name__ == "__main__":
    manager = PersonaManager()
    print("Loaded Personas:", list(manager.personas.keys()))
    print("\n--- Sample Professional System Prompt ---")
    print(manager.build_system_prompt("professional"))
