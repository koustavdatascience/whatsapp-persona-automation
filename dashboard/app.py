"""
dashboard/app.py
-----------------
Streamlit Cruise Control Console for WhatsApp Persona Automation.

Shows:
  • Pipeline status (bridge server online/offline)
  • Live decision log feed (auto-refreshes every 5 seconds)
  • Per-decision breakdown: JID, relationship, decision, reason, reply preview
  • Summary stats: total processed, reply rate, top ignored reasons

Run:
    streamlit run dashboard/app.py
"""

import json
import os
from pathlib import Path

import requests
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ── Config ────────────────────────────────────────────────────────────────────
FLASK_URL  = f"http://127.0.0.1:{os.getenv('FLASK_PORT', 5050)}"
LOG_PATH   = Path("logs") / "decision_log.jsonl"
REFRESH_MS = 5000   # auto-refresh interval in milliseconds

# ── Page setup ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="WPA Cruise Control",
    page_icon="🤖",
    layout="wide",
)

# Auto-refresh every 5 seconds
st_autorefresh(interval=REFRESH_MS, key="autorefresh")

st.title("🤖 WhatsApp Persona Automation")
st.caption("Cruise Control Console — live pipeline monitor")

# ── Helpers ───────────────────────────────────────────────────────────────────

def check_bridge_health() -> dict | None:
    """Ping the Flask bridge /health endpoint. Returns dict or None on failure."""
    try:
        r = requests.get(f"{FLASK_URL}/health", timeout=2)
        return r.json() if r.ok else None
    except Exception:
        return None


def load_log(n: int = 100) -> list[dict]:
    """Load last n lines from the local decision log file."""
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


# ── Section 1: Bridge status ──────────────────────────────────────────────────
st.subheader("Bridge Status")

health = check_bridge_health()
col1, col2, col3 = st.columns(3)

if health:
    col1.metric("Bridge Server", "🟢 Online")
    col2.metric("Pipeline", "✅ Ready" if health.get("pipeline_available") else "⚠️ Degraded")
    col3.metric("Last Checked", health.get("timestamp", "—")[:19].replace("T", " "))
else:
    col1.metric("Bridge Server", "🔴 Offline")
    col2.metric("Pipeline", "—")
    col3.metric("Last Checked", "—")
    st.warning("Bridge server is not running. Start it with: `python -m bridge.bridge_server`")

st.divider()

# ── Section 2: Summary stats ──────────────────────────────────────────────────
st.subheader("Summary")

log_entries = load_log(200)

if log_entries:
    total      = len(log_entries)
    replied    = sum(1 for e in log_entries if e.get("decision") == "reply")
    ignored    = total - replied
    reply_rate = (replied / total * 100) if total else 0

    # Top ignore reasons
    reasons = {}
    for e in log_entries:
        if e.get("decision") == "ignore":
            r = e.get("reason", "unknown")
            reasons[r] = reasons.get(r, 0) + 1
    top_reason = max(reasons, key=reasons.get) if reasons else "—"

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Total Processed", total)
    s2.metric("Replied",         replied)
    s3.metric("Ignored",         ignored)
    s4.metric("Reply Rate",      f"{reply_rate:.1f}%")

    st.caption(f"Most common ignore reason: **{top_reason}**")
else:
    st.info("No decisions logged yet. Waiting for messages...")

st.divider()

# ── Section 3: Live decision feed ─────────────────────────────────────────────
st.subheader("Live Decision Feed")

if log_entries:
    # Show newest first
    for entry in reversed(log_entries[-50:]):
        decision   = entry.get("decision", "?")
        jid        = entry.get("jid", "?")
        rel        = entry.get("relationship", "?")
        reason     = entry.get("reason", "")
        text       = entry.get("text", "")
        reply      = entry.get("reply", "")
        ts         = entry.get("timestamp", "")[:19].replace("T", " ") if entry.get("timestamp") else ""

        icon = "✅" if decision == "reply" else "🚫"
        color = "green" if decision == "reply" else "red"

        with st.expander(f"{icon} [{ts}] {jid} — {rel} → **{decision.upper()}**", expanded=False):
            c1, c2 = st.columns(2)
            c1.markdown(f"**JID:** `{jid}`")
            c1.markdown(f"**Relationship:** `{rel}`")
            c1.markdown(f"**Decision:** :{color}[{decision.upper()}]")
            c1.markdown(f"**Reason:** {reason}")
            c2.markdown(f"**Incoming:** {text or '—'}")
            if reply:
                c2.markdown(f"**Reply sent:** {reply}")
else:
    st.info("Decision log is empty.")

st.divider()
st.caption("Auto-refreshes every 5 seconds · WhatsApp Persona Automation")
