"""
agent/decision_engine.py
-------------------------
Layered reply-or-ignore pipeline for the WLM autonomous reply system.

Public API
----------
    should_reply(message, relationship) -> tuple[bool, str]

    message  : dict with keys —
                 from_me       (bool)   – True if we sent this message
                 text          (str)    – message body (may be empty for media)
                 message_type  (str)    – "text" | "image" | "audio" | "video" | …
                 is_forwarded  (bool)   – True if the message was forwarded
    relationship : str  – tier from the router, e.g. "friend", "professional"

Returns
-------
    (should_reply: bool, reason: str)

Layers run cheapest-first to avoid unnecessary LLM calls:
    1. HARD RULES     — instant, no LLM
    2. SIGNAL RULES   — instant, no LLM
    3. INTENT CHECK   — one Gemini call (gemini-3.6-flash)
    4. DEFAULT        — reply ("passed all gates")

Every decision is appended as a JSON line to logs/decision_log.jsonl.
"""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from google import genai

from config.constants import ONE_WORD_ACKS

load_dotenv()

# ── Gemini client — initialised once at module level ─────────────────────────
_gemini = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
_INTENT_MODEL = "gemini-3.6-flash"

# ── Log file ──────────────────────────────────────────────────────────────────
_LOG_DIR  = Path("logs")
_LOG_FILE = _LOG_DIR / "decision_log.jsonl"

# ── Intent labels — the ONLY two strings the LLM is allowed to return ─────────
_SAFE_LABEL    = "safe_to_auto_reply"
_SERIOUS_LABEL = "needs_human_money_or_serious"

# ── Intent classification prompt ──────────────────────────────────────────────
_INTENT_PROMPT = """\
Classify the WhatsApp message below as exactly one of these two labels:
  safe_to_auto_reply
  needs_human_money_or_serious

Use "needs_human_money_or_serious" for anything involving:
  - money, payments, loans, financial transactions
  - medical or legal matters
  - genuine emergencies or urgent personal matters
  - requests that require a binding human decision
  - genuine ambiguity where auto-replying could cause real harm

Use "safe_to_auto_reply" for everything else.

CRITICAL: Reply with ONLY the label — no punctuation, no explanation,
no extra words. Any other response is treated as needs_human_money_or_serious.

Message: {text}"""


# ── Logging helper ────────────────────────────────────────────────────────────

def _log(text: str, relationship: str, decision: str, reason: str) -> None:
    """Appends one JSON decision record to logs/decision_log.jsonl."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "text":         text,
        "relationship": relationship,
        "decision":     decision,   # "reply" or "ignore"
        "reason":       reason,
    }
    with _LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Public function ───────────────────────────────────────────────────────────

def should_reply(message: dict, relationship: str) -> tuple[bool, str]:
    """
    Run the layered reply-or-ignore pipeline.

    Parameters
    ----------
    message      : dict — from_me (bool), text (str), message_type (str),
                   is_forwarded (bool)
    relationship : str  — routing tier from agent/router.py

    Returns
    -------
    (True, reason)   → auto-reply is safe
    (False, reason)  → ignore / escalate to human
    """
    from_me      = bool(message.get("from_me", False))
    text         = message.get("text", "") or ""
    message_type = message.get("message_type", "text") or "text"
    is_forwarded = bool(message.get("is_forwarded", False))

    # ── LAYER 1: HARD RULES (instant, no LLM) ────────────────────────────────

    if from_me:
        reason = "own message"
        _log(text, relationship, "ignore", reason)
        return False, reason

    if relationship == "group":
        reason = "group chat, not allowlisted"
        _log(text, relationship, "ignore", reason)
        return False, reason

    if relationship == "unknown":
        reason = "sender not in allowlist"
        _log(text, relationship, "ignore", reason)
        return False, reason

    # ── LAYER 2: SIGNAL RULES (instant, no LLM) ──────────────────────────────

    # Media with no text caption — nothing to ground a reply on.
    # NOTE: Session 4.1 will upgrade this to a rule-based contextual ack
    # instead of a plain ignore; for now, ignore is correct and expected.
    if message_type in ("image", "audio", "video") and not text.strip():
        reason = "media-only, no text to ground a reply"
        _log(text, relationship, "ignore", reason)
        return False, reason

    if is_forwarded:
        reason = "forwarded content, not a real question"
        _log(text, relationship, "ignore", reason)
        return False, reason

    # Strip punctuation, lowercase, check against shared ack set
    clean = re.sub(r"[^\w\s]", "", text.strip().lower())
    if clean in ONE_WORD_ACKS:
        reason = "low-signal ack, no reply needed"
        _log(text, relationship, "ignore", reason)
        return False, reason

    # ── LAYER 3: INTENT CHECK (one LLM call) ─────────────────────────────────

    prompt = _INTENT_PROMPT.format(text=text)

    try:
        response = _gemini.models.generate_content(
            model=_INTENT_MODEL,
            contents=prompt,
        )
        raw_label = response.text.strip() if response.text else ""
    except Exception as exc:
        # Connection / API error — fail CLOSED (do not auto-reply)
        raw_label = ""
        print(f"[decision_engine] Gemini error: {exc}")

    # Normalise: strip whitespace, lowercase for comparison only
    normalised = raw_label.strip().lower()

    if normalised == _SAFE_LABEL:
        reason = "passed all gates"
        _log(text, relationship, "reply", reason)
        return True, reason

    # Anything other than the exact safe label → treat as serious.
    # Log the raw unexpected response so we can debug it.
    if normalised != _SERIOUS_LABEL:
        print(f"[decision_engine] Unexpected LLM label: {repr(raw_label)!r} — treating as serious")

    reason = "needs_human_money_or_serious"
    _log(text, relationship, "ignore", reason)
    return False, reason
