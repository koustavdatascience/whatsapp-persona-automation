"""
config/settings.py
-------------------
Runtime settings helpers — read from config/settings.json, with safe
defaults so the caller never crashes over a missing or malformed file.

Public API
----------
    load_settings()         -> dict
    is_dry_run()            -> bool
    is_kill_switch_active() -> bool
    get_allowlist()         -> set[str]
    enforce_allowlist(jid)  -> bool
"""

import json
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_SETTINGS_PATH    = Path("config") / "settings.json"
_RELATIONSHIP_MAP = Path("config") / "relationship_map.json"
_KILL_SWITCH_FLAG = Path("kill_switch.flag")

# ── Safe defaults — returned whenever settings.json is missing or broken ──────
_DEFAULTS: dict = {
    "dry_run":           True,
    "min_delay_seconds": 3,
    "max_delay_seconds": 12,
}


# ── 1. load_settings() ────────────────────────────────────────────────────────

def load_settings() -> dict:
    """
    Read config/settings.json and return its contents merged with defaults.

    Returns _DEFAULTS unchanged if the file is missing, empty, or fails
    to parse — never raises, never crashes the caller.

    Returns
    -------
    dict with at least:
        "dry_run"           : bool  (default True)
        "min_delay_seconds" : int   (default 3)
        "max_delay_seconds" : int   (default 12)
    """
    try:
        text = _SETTINGS_PATH.read_text(encoding="utf-8").strip()
        if not text:
            return dict(_DEFAULTS)
        data = json.loads(text)
        if not isinstance(data, dict):
            return dict(_DEFAULTS)
        # Merge: file values override defaults, defaults fill missing keys
        merged = dict(_DEFAULTS)
        merged.update(data)
        return merged
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)


# ── 2. is_dry_run() ───────────────────────────────────────────────────────────

def is_dry_run() -> bool:
    """
    Return True if the system is in dry-run mode (no messages sent).
    Reads dry_run from config/settings.json via load_settings().
    Defaults to True — safe by default.
    """
    return bool(load_settings().get("dry_run", True))


# ── 3. is_kill_switch_active() ────────────────────────────────────────────────

def is_kill_switch_active() -> bool:
    """
    Return True if kill_switch.flag exists in the repo root.

    Creating that file immediately stops all autonomous sending regardless
    of any other setting. Delete the file to re-enable.
    """
    return _KILL_SWITCH_FLAG.exists()


# ── 4. get_allowlist() ────────────────────────────────────────────────────────

def get_allowlist() -> set[str]:
    """
    Return the set of phone numbers allowed to receive auto-replies.

    Derived directly from config/relationship_map.json — every key whose
    value is NOT "unknown" and is not the literal "_default" key.

    This means the allowlist stays in sync with the relationship map
    automatically — no separate hand-typed list that could drift out of sync.

    Returns
    -------
    set[str]  — bare phone number strings (no "@..." suffix),
                e.g. {"919812345670", "919812345671"}
                Empty set if the file is missing or malformed.
    """
    try:
        data: dict = json.loads(
            _RELATIONSHIP_MAP.read_text(encoding="utf-8")
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()

    return {
        key
        for key, value in data.items()
        if key != "_default" and value != "unknown"
    }


# ── 5. enforce_allowlist() ────────────────────────────────────────────────────

def enforce_allowlist(jid: str) -> bool:
    """
    Return True only if the JID's phone number is in the allowlist.

    Strips the "@..." suffix using the same logic as agent/router.py —
    everything before the first "@" is the bare phone number.

    Parameters
    ----------
    jid : WhatsApp JID string, e.g.:
            "919812345670@s.whatsapp.net"
            "919812345670@lid"
            "120363012345678901@g.us"

    Returns
    -------
    bool — True if the number is in get_allowlist(), False otherwise.
           Always returns False for empty/non-string input.
    """
    if not jid or not isinstance(jid, str):
        return False

    at_pos = jid.find("@")
    number = jid[:at_pos] if at_pos != -1 else jid.strip()

    if not number:
        return False

    return number in get_allowlist()
