"""
agent/bridge.py
----------------
Flask bridge app — single POST endpoint /process that runs the full agent
pipeline and logs every decision to logs/console_feed.jsonl.

Endpoint
--------
    POST /process
    Body (JSON):
        {
            "jid":          str,   # WhatsApp JID
            "text":         str,   # message text
            "message_type": str,   # "text" | "image" | "video" | ...
            "is_forwarded": bool,
            "from_me":      bool
        }

    Response (JSON):
        {
            "should_reply": bool,
            "reply":        str | null,
            "relationship": str,
            "reason":       str
        }

Log entry written to logs/console_feed.jsonl on every request:
        {
            "timestamp":       ISO-8601 str,
            "jid":             str,
            "relationship":    str,
            "decision":        "reply" | "ignore",
            "reason":          str,
            "reply":           str | null,
            "retrieval_trace": [ { "their_message": str, "my_reply": str, "distance": float }, ... ]
        }

Run
---
    python -m agent.bridge
    (or)
    python agent/bridge.py

Runs on port 5001 (not 5000 — conflicts with AirPlay Receiver on macOS).
debug=False so the server does not restart on every code change.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

# ── Lazy-import agent modules — server starts even if scipy is blocked ────────
try:
    from agent.router import resolve_relationship
    from agent.decision_engine import should_reply
    from agent.generator import generate_reply
    from ingestion.retrieval import retrieve_similar
    _PIPELINE_AVAILABLE = True
except Exception as _e:
    print(f"[agent.bridge] WARNING: pipeline unavailable ({_e})")
    _PIPELINE_AVAILABLE = False

# ── Config ────────────────────────────────────────────────────────────────────
PORT          = int(os.getenv("AGENT_BRIDGE_PORT", 5001))
LOG_DIR       = Path("logs")
CONSOLE_LOG   = LOG_DIR / "console_feed.jsonl"

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _append_log(entry: dict) -> None:
    """Append a single JSON line to logs/console_feed.jsonl."""
    LOG_DIR.mkdir(exist_ok=True)
    with CONSOLE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── Endpoint ──────────────────────────────────────────────────────────────────

@app.route("/process", methods=["POST"])
def process():
    """
    Run the full agent pipeline for an incoming WhatsApp message.

    Steps:
        1. resolve_relationship(jid)          → relationship tier
        2. should_reply(message_dict, rel)    → (bool, reason)
        3. generate_reply(text, rel)          → reply text  [only if approved]
        4. retrieve_similar(rel, text, k=3)   → retrieval_trace  [for logging]
        5. Append one line to logs/console_feed.jsonl
        6. Return JSON response
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid or missing JSON body"}), 400

    jid          = data.get("jid", "")
    text         = data.get("text", "")
    message_type = data.get("message_type", "text")
    is_forwarded = data.get("is_forwarded", False)
    from_me      = data.get("from_me", False)

    print(f"[agent.bridge] ← {jid} | {message_type} | {text[:60]!r}")

    # Pipeline unavailable — return graceful degradation
    if not _PIPELINE_AVAILABLE:
        entry = {
            "timestamp":       datetime.now(timezone.utc).isoformat(),
            "jid":             jid,
            "relationship":    "unknown",
            "decision":        "ignore",
            "reason":          "pipeline unavailable (scipy/sentence-transformers blocked)",
            "reply":           None,
            "retrieval_trace": [],
        }
        _append_log(entry)
        return jsonify({
            "should_reply": False,
            "reply":        None,
            "relationship": "unknown",
            "reason":       entry["reason"],
        })

    # Step 1 — resolve relationship
    relationship, _ = resolve_relationship(jid)

    # Step 2 — build message dict and run decision gate
    message_dict = {
        "from_me":      from_me,
        "text":         text,
        "message_type": message_type,
        "is_forwarded": is_forwarded,
    }
    ok, reason = should_reply(message_dict, relationship)

    # Step 3 — generate reply if approved
    # Special case: media_ack replies are rule-based and carried in the reason
    # string as "media_ack::<reply text>" — no LLM call needed.
    reply = None
    if ok:
        if reason.startswith("media_ack::"):
            reply = reason.split("::", 1)[1]
            reason = "media_ack"
        else:
            reply = generate_reply(text, relationship)

    # Step 4 — retrieval trace for logging/display (purely informational)
    retrieval_trace = []
    try:
        retrieval_trace = retrieve_similar(relationship, text, k=3)
    except Exception as exc:
        print(f"[agent.bridge] retrieval trace skipped ({exc})")

    # Step 5 — log the decision
    entry = {
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "jid":             jid,
        "relationship":    relationship,
        "decision":        "reply" if ok else "ignore",
        "reason":          reason,
        "reply":           reply,
        "retrieval_trace": retrieval_trace,
    }
    _append_log(entry)

    print(f"[agent.bridge] → {'REPLY' if ok else 'IGNORE'} | {reason}")

    # Step 6 — respond
    return jsonify({
        "should_reply": ok,
        "reply":        reply,
        "relationship": relationship,
        "reason":       reason,
    })


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[agent.bridge] Starting on http://127.0.0.1:{PORT}/process ...")
    app.run(host="127.0.0.1", port=PORT, debug=False)
