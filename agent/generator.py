"""
agent/generator.py
-------------------
Reply generation layer for the WLM autonomous reply system.

Public API
----------
    generate_reply(incoming_text: str, relationship: str) -> str

    incoming_text  : the raw text of the incoming WhatsApp message
    relationship   : tier string — must match a key in persona.json's
                     "relationships" dict (e.g. "gf", "roshun", "professional")
                     or fall back to top-level persona defaults

Returns
-------
    str — the generated reply text, stripped of leading/trailing whitespace.
          Never None, never crashes — always returns a safe string.

Pipeline
--------
    1. Load persona/persona.json  (top-level + relationship-specific data)
    2. Call retrieve_similar(relationship, incoming_text, k=3) for RAG context
       — gracefully handles empty lists (Chroma offline or no history yet)
    3. Build a gemini-3.5-flash prompt combining:
         • Koustav's identity and hard rules
         • Relationship-specific tone, language, hinglish_ratio, avg length
         • Retrieved (their_message → my_reply) few-shot pairs (if any)
         • The new incoming message
    4. Call Gemini and return the reply text.
       — On None/empty response (safety filter): return a safe fallback string.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from ingestion.retrieval import retrieve_similar

load_dotenv()

# ── Constants ─────────────────────────────────────────────────────────────────
_PERSONA_PATH = Path("persona") / "persona.json"
_GEMINI_MODEL = "gemini-3.5-flash"
_FALLBACK     = "[no reply generated — check response.candidates for details]"

# ── Gemini client — initialised once at module level ─────────────────────────
_gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))


# ── Internal helpers ──────────────────────────────────────────────────────────

def _load_persona() -> dict:
    """Load and return the full persona.json dict."""
    with _PERSONA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _build_prompt(
    persona: dict,
    relationship: str,
    incoming_text: str,
    retrieved_pairs: list[dict],
) -> str:
    """
    Assemble the generation prompt from persona data, RAG pairs, and the
    new incoming message.

    Parameters
    ----------
    persona          : full persona.json dict
    relationship     : tier string
    incoming_text    : new message to reply to
    retrieved_pairs  : list of {their_message, my_reply, distance} dicts
                       (may be empty)
    """
    identity        = persona.get("identity", "Koustav")
    work            = persona.get("work_and_interests", "")
    hard_rules      = persona.get("hard_rules", [])
    global_hinglish = persona.get("hinglish_ratio", "0%")
    global_avg_len  = persona.get("avg_message_length_words", 2)

    # Relationship-specific overrides (fall back to global defaults if tier
    # is not present in the relationships map)
    rel_data    = persona.get("relationships", {}).get(relationship.lower(), {})
    tone        = rel_data.get("tone", "Natural, conversational")
    language    = rel_data.get("language", "English")
    hinglish    = rel_data.get("hinglish_ratio", global_hinglish)
    avg_len     = global_avg_len   # persona.json stores one global avg length
    examples    = rel_data.get("example_replies", [])

    # ── Build prompt ──────────────────────────────────────────────────────────
    lines = [
        f"You are {identity}.",
        f"Work & interests: {work}",
        "",
        "[HARD RULES — never break these]",
    ]
    for rule in hard_rules:
        lines.append(f"- {rule}")

    lines += [
        "",
        f"[RELATIONSHIP TIER: {relationship.upper()}]",
        f"Tone        : {tone}",
        f"Language    : {language}",
        f"Hinglish %  : {hinglish}",
        f"Avg length  : ~{avg_len} words",
        "",
    ]

    # Few-shot examples from persona.json
    if examples:
        lines.append("[STYLE EXAMPLES — how you typically reply in this tier]")
        for ex in examples:
            lines.append(f'  "{ex}"')
        lines.append("")

    # RAG-retrieved pairs — skip section entirely if list is empty
    if retrieved_pairs:
        lines.append("[RETRIEVED PAST CONVERSATION PAIRS — use as style reference]")
        for pair in retrieved_pairs:
            lines.append(f'  Them : "{pair["their_message"]}"')
            lines.append(f'  You  : "{pair["my_reply"]}"')
            lines.append("")

    lines += [
        "[TASK]",
        f'Reply to this incoming WhatsApp message: "{incoming_text}"',
        "",
        "Output ONLY the reply text — no labels, no quotes, no explanation.",
    ]

    return "\n".join(lines)


# ── Public function ───────────────────────────────────────────────────────────

def generate_reply(incoming_text: str, relationship: str) -> str:
    """
    Generate a reply to an incoming WhatsApp message.

    Parameters
    ----------
    incoming_text  : raw text of the incoming message
    relationship   : relationship tier (e.g. "gf", "roshun", "professional")

    Returns
    -------
    str — reply text, stripped of whitespace.
          Returns a safe fallback string on API / safety-filter failures.
          Never raises, never returns None.
    """
    # 1. Load persona
    persona = _load_persona()

    # 2. Retrieve similar past pairs — handle empty result gracefully
    try:
        retrieved_pairs = retrieve_similar(relationship, incoming_text, k=3)
    except Exception as exc:
        # Chroma offline or connection error — continue without RAG context
        print(f"[generator] retrieval skipped ({exc}); generating from persona only")
        retrieved_pairs = []

    # 3. Build prompt
    prompt = _build_prompt(persona, relationship, incoming_text, retrieved_pairs)

    # 4. Call Gemini
    try:
        response = _gemini.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
        )
        reply = response.text.strip() if response.text else ""
    except Exception as exc:
        print(f"[generator] Gemini error: {exc}")
        reply = ""

    return reply if reply else _FALLBACK


# ── Quick manual test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_cases = [
        ("Hey babe, you coming home tonight?",           "gf"),
        ("Bhai lobby bana, khelbi?",                     "roshun"),
        ("Hey, can you send over the draft by tomorrow?", "professional"),
    ]

    for text, tier in test_cases:
        print(f"\n[{tier.upper()}] Incoming : {text!r}")
        reply = generate_reply(text, tier)
        print(f"[{tier.upper()}] Reply    : {reply!r}")
