"""
console/app.py
---------------
Streamlit live console for WhatsApp Persona Automation.

Features:
  1. Auto-refreshes every 2 seconds
  2. Live feed from logs/console_feed.jsonl — last 20 entries, newest first
     - Colored relationship badge (family=green, friend=blue,
       professional=purple, unknown/group=gray)
     - Decision (reply/ignore) with reason
     - Generated reply if any
     - Expandable retrieval trace section
  3. Sidebar: current DRY_RUN / LIVE mode (read from config/mode.txt)
  4. Sidebar metrics: total messages processed + total replies sent

Run:
    streamlit run console/app.py
"""

import json
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ── Paths ─────────────────────────────────────────────────────────────────────
LOG_FILE  = Path("logs") / "console_feed.jsonl"
MODE_FILE = Path("config") / "mode.txt"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="WPA Console",
    page_icon="💬",
    layout="wide",
)

# Auto-refresh every 2 seconds
st_autorefresh(interval=2000, key="console_refresh")

# ── Helpers ───────────────────────────────────────────────────────────────────

def read_mode() -> str:
    """Read DRY_RUN or LIVE from config/mode.txt. Defaults to DRY_RUN."""
    try:
        return MODE_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return "DRY_RUN"


def load_log(n: int = 20) -> list[dict]:
    """Return last n entries from console_feed.jsonl, or empty list."""
    if not LOG_FILE.exists():
        return []
    lines = LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    entries = []
    for line in lines[-n:]:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries


def relationship_badge(rel: str) -> str:
    """Return a colored Streamlit markdown badge for the relationship tier."""
    rel = (rel or "unknown").lower()
    if rel in ("family",):
        color = "green"
    elif rel in ("gf", "roshun", "friends", "friend", "gaming"):
        color = "blue"
    elif rel in ("professional", "client"):
        color = "violet"
    else:
        color = "gray"
    return f":{color}[{rel.upper()}]"


def decision_badge(decision: str) -> str:
    if decision == "reply":
        return ":green[✅ REPLY]"
    return ":red[🚫 IGNORE]"


def fmt_ts(ts: str) -> str:
    """Trim ISO timestamp to HH:MM:SS for display."""
    if not ts:
        return "—"
    # e.g. 2026-09-25T14:32:01.123456+00:00 → 14:32:01
    try:
        return ts[11:19]
    except Exception:
        return ts


# ── Sidebar ───────────────────────────────────────────────────────────────────
mode     = read_mode()
entries  = load_log(200)   # load all for stats

total_processed = len(entries)
total_replied   = sum(1 for e in entries if e.get("decision") == "reply")

with st.sidebar:
    st.title("⚙️ Status")

    # Mode badge
    if mode == "LIVE":
        st.markdown("**Mode:** :red[🔴 LIVE — sending enabled]")
    else:
        st.markdown("**Mode:** :orange[🟡 DRY_RUN — no messages sent]")

    st.divider()

    st.metric("Messages Processed", total_processed)
    st.metric("Replies Sent",        total_replied)

    if total_processed:
        rate = total_replied / total_processed * 100
        st.metric("Reply Rate", f"{rate:.1f}%")

    st.divider()
    st.caption("Mode is read from config/mode.txt\nSession 4.2 adds live toggle.")

# ── Main feed ─────────────────────────────────────────────────────────────────
st.title("💬 WhatsApp Persona Automation — Live Console")
st.caption("Auto-refreshes every 2 seconds · newest first")

st.divider()

# Reload last 20 for display (newest first)
display_entries = load_log(20)

if not display_entries:
    st.info("⏳ Waiting for first message...")
else:
    for entry in reversed(display_entries):
        ts       = fmt_ts(entry.get("timestamp", ""))
        jid      = entry.get("jid", "unknown")
        rel      = entry.get("relationship", "unknown")
        decision = entry.get("decision", "ignore")
        reason   = entry.get("reason", "")
        reply    = entry.get("reply") or ""
        trace    = entry.get("retrieval_trace") or []
        text     = entry.get("text", "")

        # ── Card ──────────────────────────────────────────────────────────────
        with st.container(border=True):
            col1, col2, col3 = st.columns([1, 3, 3])

            with col1:
                st.markdown(f"`{ts}`")
                st.markdown(relationship_badge(rel))
                st.markdown(decision_badge(decision))

            with col2:
                st.markdown(f"**From:** `{jid}`")
                st.markdown(f"**Reason:** {reason}")
                if text:
                    st.markdown(f"**Message:** {text}")

            with col3:
                if reply:
                    st.markdown(f"**Reply:** {reply}")
                else:
                    st.markdown("**Reply:** —")

                # Expandable retrieval trace
                if trace:
                    with st.expander(f"🔍 Retrieval trace ({len(trace)} pair{'s' if len(trace) != 1 else ''})"):
                        for i, pair in enumerate(trace, 1):
                            st.markdown(f"**{i}.** Them: *{pair.get('their_message', '')}*")
                            st.markdown(f"   You: *{pair.get('my_reply', '')}*")
                            dist = pair.get("distance")
                            if dist is not None:
                                st.caption(f"   distance: {dist:.4f}")
