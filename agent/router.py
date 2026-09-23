"""
agent/router.py
----------------
Maps an incoming WhatsApp JID (e.g. "919812345670@s.whatsapp.net") to a
relationship tier and the corresponding ChromaDB collection name.

Public API
----------
    resolve_relationship(jid, map_path) -> tuple[str, str | None]

Returns
-------
    (relationship, collection_name)

    relationship    : tier string — "friend", "family", "professional",
                      "unknown", "group", or whatever is in the map
    collection_name : "history_{relationship}"  for individual chats
                      None                      for group JIDs (never
                      retrieved against history)
"""

import json
from pathlib import Path

# ── Collection name helper ────────────────────────────────────────────────────

def _collection_for(relationship: str) -> str | None:
    """Returns the ChromaDB collection name, or None for group chats."""
    if relationship == "group":
        return None
    return f"history_{relationship}"


# ── Main public function ──────────────────────────────────────────────────────

def resolve_relationship(
    jid: str,
    map_path: str = "config/relationship_map.json",
) -> tuple[str, str | None]:
    """
    Resolve a WhatsApp JID to a (relationship, collection_name) tuple.

    Parameters
    ----------
    jid      : Raw JID string from Baileys, e.g.:
                 "919812345670@s.whatsapp.net"
                 "919812345670@lid"
                 "120363012345678901@g.us"   ← group
    map_path : Path to config/relationship_map.json (default works when
               running from the project root).

    Returns
    -------
    tuple[str, str | None]
        (relationship, collection_name)
    """

    # ── Guard: empty / non-string input ──────────────────────────────────────
    if not jid or not isinstance(jid, str):
        return ("unknown", _collection_for("unknown"))

    jid = jid.strip()

    # ── Rule 1: group JIDs end with "@g.us" — short-circuit immediately ───────
    # Group messages are never looked up in the relationship map and are never
    # retrieved against any history collection.
    if jid.endswith("@g.us"):
        return ("group", None)

    # ── Rule 2: strip the "@…" suffix to isolate the bare phone number ────────
    # Handles both "@s.whatsapp.net" and "@lid" (and any future suffix).
    at_pos = jid.find("@")
    number = jid[:at_pos] if at_pos != -1 else jid

    # After stripping, if we somehow end up with an empty string, fall back.
    if not number:
        return ("unknown", _collection_for("unknown"))

    # ── Rule 3: look up the number in the relationship map ────────────────────
    try:
        with Path(map_path).open(encoding="utf-8") as f:
            rel_map: dict[str, str] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Map missing or broken — fail safe rather than crash
        return ("unknown", _collection_for("unknown"))

    # Direct match first, then fall back to "_default", then hard-coded "unknown"
    relationship = rel_map.get(number) or rel_map.get("_default") or "unknown"

    # ── Rule 4: build the collection name ─────────────────────────────────────
    return (relationship, _collection_for(relationship))
