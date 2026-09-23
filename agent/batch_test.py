"""
agent/batch_test.py
--------------------
End-to-end batch test that exercises every gate in the decision pipeline
in a single run.

For each test case the script:
    1. Resolves the relationship via agent.router.resolve_relationship
    2. Runs agent.decision_engine.should_reply
    3. If allowed, calls agent.generator.generate_reply
    4. Prints a clean summary table

Run from the project root:
    python -m agent.batch_test
"""

import textwrap

from agent.decision_engine import should_reply
from agent.router import resolve_relationship

# generator imports sentence-transformers/chromadb at module level; those
# may be unavailable in restricted environments.  Import lazily so the rest
# of the test still runs even if the embedding stack is blocked.
try:
    from agent.generator import generate_reply as _generate_reply
    _GENERATOR_AVAILABLE = True
except Exception as _gen_import_err:
    _GENERATOR_AVAILABLE = False
    print(f"[batch_test] generator unavailable ({_gen_import_err}); "
          "REPLY cases will show '<generator unavailable>'.\n")

def generate_reply(text: str, relationship: str) -> str:
    if not _GENERATOR_AVAILABLE:
        return "<generator unavailable — sentence-transformers/chromadb blocked>"
    return _generate_reply(text, relationship)

# ── Test cases ────────────────────────────────────────────────────────────────
# Each dict has:
#   jid           : WhatsApp JID (drives relationship resolution)
#   message       : dict matching should_reply's expected shape
#   label         : short human-readable name shown in the table
#
# Phone numbers that exist in config/relationship_map.json:
#   919812345670 → friend
#   919812345671 → family
#   919812345672 → professional
#   (anything else → unknown, group JIDs → group)

TEST_CASES = [
    # ── Gate 1 — own message (from_me=True) ──────────────────────────────────
    {
        "label":   "Own message",
        "jid":     "919812345670@s.whatsapp.net",
        "message": {
            "from_me":      True,
            "text":         "Hey, I'm heading out now",
            "message_type": "text",
            "is_forwarded": False,
        },
    },

    # ── Gate 1 — group chat ───────────────────────────────────────────────────
    {
        "label":   "Group chat",
        "jid":     "120363012345678901@g.us",
        "message": {
            "from_me":      False,
            "text":         "Anyone free tonight for a game?",
            "message_type": "text",
            "is_forwarded": False,
        },
    },

    # ── Gate 1 — unknown sender ───────────────────────────────────────────────
    {
        "label":   "Unknown sender",
        "jid":     "919999999999@s.whatsapp.net",
        "message": {
            "from_me":      False,
            "text":         "Hi, is this Koustav?",
            "message_type": "text",
            "is_forwarded": False,
        },
    },

    # ── Gate 2 — media only (no caption) ─────────────────────────────────────
    {
        "label":   "Media, no caption",
        "jid":     "919812345670@s.whatsapp.net",
        "message": {
            "from_me":      False,
            "text":         "",
            "message_type": "image",
            "is_forwarded": False,
        },
    },

    # ── Gate 2 — forwarded message ────────────────────────────────────────────
    {
        "label":   "Forwarded message",
        "jid":     "919812345671@s.whatsapp.net",
        "message": {
            "from_me":      False,
            "text":         "Check out this amazing offer!",
            "message_type": "text",
            "is_forwarded": True,
        },
    },

    # ── Gate 2 — one-word ack ─────────────────────────────────────────────────
    {
        "label":   "One-word ack",
        "jid":     "919812345670@s.whatsapp.net",
        "message": {
            "from_me":      False,
            "text":         "thanks",
            "message_type": "text",
            "is_forwarded": False,
        },
    },

    # ── Gate 3 — money / serious intent (LLM gate) ───────────────────────────
    {
        "label":   "Money request",
        "jid":     "919812345672@s.whatsapp.net",
        "message": {
            "from_me":      False,
            "text":         "Can you send me 5000 rupees? I'll pay you back tomorrow.",
            "message_type": "text",
            "is_forwarded": False,
        },
    },

    # ── Passes all gates — casual friend ─────────────────────────────────────
    {
        "label":   "Casual friend (passes all)",
        "jid":     "919812345670@s.whatsapp.net",
        "message": {
            "from_me":      False,
            "text":         "Bhai lobby bana, khelbi tonight?",
            "message_type": "text",
            "is_forwarded": False,
        },
    },

    # ── Passes all gates — professional ──────────────────────────────────────
    {
        "label":   "Professional (passes all)",
        "jid":     "919812345672@s.whatsapp.net",
        "message": {
            "from_me":      False,
            "text":         "Hey, can you send over the draft by tomorrow?",
            "message_type": "text",
            "is_forwarded": False,
        },
    },
]

# ── Table helpers ─────────────────────────────────────────────────────────────

_COL_WIDTHS = {
    "message":      32,
    "relationship": 14,
    "decision":     8,
    "reason":       36,
    "reply":        40,
}

def _hr() -> str:
    return "+" + "+".join("-" * (w + 2) for w in _COL_WIDTHS.values()) + "+"

def _row(*cells) -> str:
    keys   = list(_COL_WIDTHS.keys())
    parts  = []
    for i, cell in enumerate(cells):
        width = _COL_WIDTHS[keys[i]]
        truncated = str(cell)[:width].ljust(width)
        parts.append(f" {truncated} ")
    return "|" + "|".join(parts) + "|"

def _header() -> str:
    return _row("MESSAGE", "RELATIONSHIP", "DECISION", "REASON", "REPLY")

def _trunc(text: str, width: int) -> str:
    """Truncate text with ellipsis if longer than width."""
    text = text.replace("\n", " ")
    return text if len(text) <= width else text[: width - 1] + "…"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("\n" + "=" * 80)
    print("  WLM BATCH PIPELINE TEST")
    print("=" * 80)
    print(_hr())
    print(_header())
    print(_hr())

    for case in TEST_CASES:
        jid      = case["jid"]
        message  = case["message"]
        label    = case["label"]

        # Step 1 — resolve relationship
        relationship, _ = resolve_relationship(jid)

        # Step 2 — decision gate
        ok, reason = should_reply(message, relationship)
        decision   = "REPLY" if ok else "IGNORE"

        # Step 3 — generate reply (only if allowed through)
        reply = ""
        if ok:
            reply = generate_reply(message["text"], relationship)

        # Build display strings
        msg_display    = _trunc(message["text"] or f"<{message['message_type']}>",
                                _COL_WIDTHS["message"])
        reason_display = _trunc(reason,  _COL_WIDTHS["reason"])
        reply_display  = _trunc(reply,   _COL_WIDTHS["reply"])

        print(_row(msg_display, relationship, decision, reason_display, reply_display))

    print(_hr())
    print()

    # ── Per-case verbose output ───────────────────────────────────────────────
    print("=" * 80)
    print("  VERBOSE DETAIL")
    print("=" * 80)

    for i, case in enumerate(TEST_CASES, 1):
        jid          = case["jid"]
        message      = case["message"]
        label        = case["label"]

        relationship, _ = resolve_relationship(jid)
        ok, reason      = should_reply(message, relationship)
        decision        = "REPLY ✓" if ok else "IGNORE ✗"

        reply = ""
        if ok:
            reply = generate_reply(message["text"], relationship)

        print(f"\n[{i:02d}] {label}")
        print(f"      JID          : {jid}")
        print(f"      Relationship : {relationship}")
        msg_text = message["text"] or f"<{message['message_type']}>"
        print(f"      Message      : {msg_text!r}")
        print(f"      Decision     : {decision}")
        print(f"      Reason       : {reason}")
        if reply:
            wrapped = textwrap.fill(reply, width=68, initial_indent=" " * 18,
                                    subsequent_indent=" " * 18)
            print(f"      Reply        :{wrapped[17:]}")

    print()


if __name__ == "__main__":
    main()
