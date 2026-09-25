"""
bridge/bridge_server.py
------------------------
Flask bridge server — the handoff point between the Node.js Baileys client
and the Python agent pipeline.

Flow:
    Node (whatsapp_client.js)
        → POST /incoming  { jid, from_me, text, message_type, is_forwarded, timestamp }
        ← JSON            { reply: "..." }   or   { reply: null, reason: "..." }

Endpoints:
    POST /incoming   — main message handler
    GET  /health     — liveness check for the dashboard
    GET  /log        — returns last N decision log entries (for the dashboard)

Run:
    python -m bridge.bridge_server
    (or)
    python bridge/bridge_server.py
"""

import json
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, request

load_dotenv()

# ── Lazy-import agent modules so the server still starts even if the
#    embedding stack (sentence-transformers/scipy) is blocked ─────────────────
try:
    from agent.router import resolve_relationship
    from agent.decision_engine import should_reply
    from agent.generator import generate_reply
    _PIPELINE_AVAILABLE = True
except Exception as _e:
    print(f"[bridge_server] WARNING: agent pipeline unavailable ({_e})")
    _PIPELINE_AVAILABLE = False

# ── Config ────────────────────────────────────────────────────────────────────
FLASK_PORT    = int(os.getenv("FLASK_PORT", 5050))
LOG_PATH      = Path("logs") / "decision_log.jsonl"
MAX_LOG_LINES = 200   # cap returned by /log endpoint

app = Flask(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_log(n: int = 50) -> list[dict]:
    """Return the last n lines of the decision log as a list of dicts."""
    if not LOG_PATH.exists():
        return []
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines[-n:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/health", methods=["GET"])
def health():
    """Liveness check — returns pipeline availability status."""
    return jsonify({
        "status":             "ok",
        "pipeline_available": _PIPELINE_AVAILABLE,
        "timestamp":          datetime.utcnow().isoformat(),
    })


@app.route("/log", methods=["GET"])
def log():
    """Return last N decision log entries for the dashboard."""
    n = min(int(request.args.get("n", 50)), MAX_LOG_LINES)
    return jsonify(_read_log(n))


@app.route("/incoming", methods=["POST"])
def incoming():
    """
    Main endpoint — receives a message from Baileys, runs the full agent
    pipeline, and returns a reply (or null if the message should be ignored).

    Expected JSON body:
        {
            "jid":          "919812345670@s.whatsapp.net",
            "from_me":      false,
            "text":         "Bhai khelbi tonight?",
            "message_type": "text",
            "is_forwarded": false,
            "timestamp":    1234567890
        }

    Response:
        { "reply": "Haa bhai, aaschi!" }        — approved, reply text
        { "reply": null, "reason": "own msg" }   — ignored, reason string
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "invalid JSON body"}), 400

    jid          = data.get("jid", "")
    from_me      = data.get("from_me", False)
    text         = data.get("text", "")
    message_type = data.get("message_type", "text")
    is_forwarded = data.get("is_forwarded", False)

    print(f"[bridge_server] ← {jid} | {message_type} | {text[:60]!r}")

    # Pipeline unavailable — fail gracefully
    if not _PIPELINE_AVAILABLE:
        return jsonify({
            "reply":  None,
            "reason": "pipeline unavailable (sentence-transformers blocked)",
        })

    # Step 1 — resolve relationship tier
    relationship, _ = resolve_relationship(jid)

    # Step 2 — build message dict for decision engine
    message = {
        "from_me":      from_me,
        "text":         text,
        "message_type": message_type,
        "is_forwarded": is_forwarded,
    }

    # Step 3 — decision gate
    ok, reason = should_reply(message, relationship)

    if not ok:
        print(f"[bridge_server] IGNORE → {reason}")
        return jsonify({"reply": None, "reason": reason})

    # Step 4 — generate reply
    reply = generate_reply(text, relationship)
    print(f"[bridge_server] REPLY  → {reply[:60]!r}")

    return jsonify({"reply": reply})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[bridge_server] Starting on port {FLASK_PORT} ...")
    app.run(host="127.0.0.1", port=FLASK_PORT, debug=False)
