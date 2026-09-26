"""
console/app.py
---------------
Streamlit live console for WhatsApp Persona Automation.

Session 4.2 additions to sidebar:
  1. DRY_RUN / LIVE toggle — writes dry_run to config/settings.json atomically
  2. min_delay_seconds / max_delay_seconds number inputs — validated, atomic write
  3. 🔴 KILL SWITCH button — creates kill_switch.flag; Clear button deletes it
  4. All settings writes are atomic (write temp file, rename into place)

Everything from Session 4.1 (live feed, retrieval trace, metrics) unchanged.

Run:
    streamlit run console/app.py
"""

import json
import os
import tempfile
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ── Paths ─────────────────────────────────────────────────────────────────────
LOG_FILE        = Path("logs") / "console_feed.jsonl"
SETTINGS_FILE   = Path("config") / "settings.json"
KILL_SWITCH     = Path("kill_switch.flag")

# ── Safe defaults ─────────────────────────────────────────────────────────────
_DEFAULTS = {"dry_run": True, "min_delay_seconds": 3, "max_delay_seconds": 12}

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="WPA Console",
    page_icon="💬",
    layout="wide",
)

# Auto-refresh every 2 seconds
st_autorefresh(interval=2000, key="console_refresh")


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    """Read config/settings.json, return merged with defaults. Never raises."""
    try:
        text = SETTINGS_FILE.read_text(encoding="utf-8").strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            return dict(_DEFAULTS)
        return {**_DEFAULTS, **data}
    except Exception:
        return dict(_DEFAULTS)


def save_settings(updates: dict) -> None:
    """
    Merge updates into the current settings and write atomically.
    Atomic write: write to a temp file in the same directory, then rename
    into place — a concurrent reader never sees a half-written file.
    """
    current = load_settings()
    current.update(updates)
    dir_path = SETTINGS_FILE.parent
    # Write to a temp file in the same directory so rename is atomic
    fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        os.replace(tmp_path, SETTINGS_FILE)   # atomic on all OS
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


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
    if not ts:
        return "—"
    try:
        return ts[11:19]
    except Exception:
        return ts


# ── Load current state ────────────────────────────────────────────────────────
settings        = load_settings()
kill_active     = KILL_SWITCH.exists()
all_entries     = load_log(200)
total_processed = len(all_entries)
total_replied   = sum(1 for e in all_entries if e.get("decision") == "reply")


# ── Kill switch warning banner (top of page, before sidebar) ─────────────────
if kill_active:
    st.error(
        "🔴 **KILL SWITCH IS ACTIVE** — all autonomous sending is halted. "
        "Use the sidebar to clear it.",
        icon="🚨",
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Controls")

    # ── 1. DRY_RUN / LIVE toggle ──────────────────────────────────────────────
    st.subheader("Mode")
    dry_run_current = bool(settings.get("dry_run", True))
    mode_label      = "DRY_RUN" if dry_run_current else "LIVE"
    mode_color      = ":orange[🟡 DRY_RUN — no messages sent]" if dry_run_current else ":red[🔴 LIVE — sending enabled]"
    st.markdown(f"Current: {mode_color}")

    new_mode = st.radio(
        "Set mode",
        options=["DRY_RUN", "LIVE"],
        index=0 if dry_run_current else 1,
        horizontal=True,
        label_visibility="collapsed",
    )
    if st.button("Apply mode", use_container_width=True):
        save_settings({"dry_run": new_mode == "DRY_RUN"})
        st.success(f"Mode set to {new_mode}")
        st.rerun()

    st.divider()

    # ── 2. Delay settings ─────────────────────────────────────────────────────
    st.subheader("Reply Delay")
    min_val = int(settings.get("min_delay_seconds", 3))
    max_val = int(settings.get("max_delay_seconds", 12))

    new_min = st.number_input(
        "Min delay (seconds)", min_value=1, max_value=60,
        value=min_val, step=1,
    )
    new_max = st.number_input(
        "Max delay (seconds)", min_value=1, max_value=120,
        value=max_val, step=1,
    )

    if st.button("Apply delay", use_container_width=True):
        if new_min <= 0 or new_max <= 0:
            st.error("Both values must be positive.")
        elif new_min >= new_max:
            st.error("Min must be less than max.")
        else:
            save_settings({"min_delay_seconds": new_min, "max_delay_seconds": new_max})
            st.success(f"Delay set to {new_min}–{new_max}s")
            st.rerun()

    st.divider()

    # ── 3. Kill switch ────────────────────────────────────────────────────────
    st.subheader("Kill Switch")
    if kill_active:
        st.markdown(":red[🔴 ACTIVE — sending halted]")
        if st.button("✅ Clear kill switch", use_container_width=True, type="primary"):
            try:
                KILL_SWITCH.unlink(missing_ok=True)
                st.success("Kill switch cleared.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not remove flag: {e}")
    else:
        st.markdown(":green[🟢 Inactive]")
        if st.button("🔴 ACTIVATE KILL SWITCH", use_container_width=True, type="primary"):
            KILL_SWITCH.touch()
            st.warning("Kill switch activated. All sending halted.")
            st.rerun()

    st.divider()

    # ── Metrics ───────────────────────────────────────────────────────────────
    st.metric("Messages Processed", total_processed)
    st.metric("Replies Sent", total_replied)
    if total_processed:
        st.metric("Reply Rate", f"{total_replied / total_processed * 100:.1f}%")


# ── Main feed ─────────────────────────────────────────────────────────────────
st.title("💬 WhatsApp Persona Automation — Live Console")
st.caption("Auto-refreshes every 2 seconds · newest first")

st.divider()

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

                if trace:
                    with st.expander(f"🔍 Retrieval trace ({len(trace)} pair{'s' if len(trace) != 1 else ''})"):
                        for i, pair in enumerate(trace, 1):
                            st.markdown(f"**{i}.** Them: *{pair.get('their_message', '')}*")
                            st.markdown(f"   You: *{pair.get('my_reply', '')}*")
                            dist = pair.get("distance")
                            if dist is not None:
                                st.caption(f"   distance: {dist:.4f}")
