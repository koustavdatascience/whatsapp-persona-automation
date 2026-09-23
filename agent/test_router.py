"""
agent/test_router.py
---------------------
pytest suite for agent/router.py  →  resolve_relationship()

Run from the project root:
    python3 -m pytest agent/test_router.py -v
"""

import json
import pytest
from pathlib import Path

from agent.router import resolve_relationship

# ── Fixture: write a temp relationship_map.json for tests ────────────────────

@pytest.fixture()
def map_file(tmp_path: Path) -> str:
    """Creates a temporary relationship map and returns its path string."""
    data = {
        "_default":      "unknown",
        "919812345670":  "friend",
        "919812345671":  "family",
        "919812345672":  "professional",
    }
    p = tmp_path / "relationship_map.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


# ── 1. Known numbers resolve correctly ───────────────────────────────────────

def test_known_friend(map_file):
    rel, col = resolve_relationship("919812345670@s.whatsapp.net", map_file)
    assert rel == "friend"
    assert col == "history_friend"

def test_known_family(map_file):
    rel, col = resolve_relationship("919812345671@s.whatsapp.net", map_file)
    assert rel == "family"
    assert col == "history_family"

def test_known_professional(map_file):
    rel, col = resolve_relationship("919812345672@s.whatsapp.net", map_file)
    assert rel == "professional"
    assert col == "history_professional"

def test_known_number_with_lid_suffix(map_file):
    """@lid suffix should be stripped just like @s.whatsapp.net."""
    rel, col = resolve_relationship("919812345670@lid", map_file)
    assert rel == "friend"
    assert col == "history_friend"


# ── 2. Unknown number falls back to _default ─────────────────────────────────

def test_unknown_number_falls_back_to_default(map_file):
    rel, col = resolve_relationship("919999999999@s.whatsapp.net", map_file)
    assert rel == "unknown"
    assert col == "history_unknown"

def test_default_used_when_key_missing(tmp_path):
    """Map with no matching key but a _default returns the default."""
    data = {"_default": "family"}
    p = tmp_path / "map.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    rel, col = resolve_relationship("919000000000@s.whatsapp.net", str(p))
    assert rel == "family"
    assert col == "history_family"


# ── 3. Group JIDs always return ("group", None) ───────────────────────────────

def test_group_jid_returns_group_none(map_file):
    rel, col = resolve_relationship("120363012345678901@g.us", map_file)
    assert rel == "group"
    assert col is None

def test_group_jid_ignores_map_even_if_number_matches(tmp_path):
    """Even if the number before @g.us is in the map, group wins."""
    data = {"_default": "unknown", "120363012345678901": "friend"}
    p = tmp_path / "map.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    rel, col = resolve_relationship("120363012345678901@g.us", str(p))
    assert rel == "group"
    assert col is None


# ── 4. Malformed / edge-case JIDs don't crash ────────────────────────────────

def test_empty_string_jid(map_file):
    rel, col = resolve_relationship("", map_file)
    assert rel == "unknown"
    assert col == "history_unknown"

def test_none_jid(map_file):
    rel, col = resolve_relationship(None, map_file)
    assert rel == "unknown"
    assert col == "history_unknown"

def test_jid_with_no_at_sign(map_file):
    """A bare number with no @ suffix should still resolve if it's in the map."""
    rel, col = resolve_relationship("919812345670", map_file)
    assert rel == "friend"
    assert col == "history_friend"

def test_jid_only_at_sign(map_file):
    """'@' with nothing before it → empty number → falls back to unknown."""
    rel, col = resolve_relationship("@s.whatsapp.net", map_file)
    assert rel == "unknown"
    assert col == "history_unknown"


# ── 5. Missing or broken map file ────────────────────────────────────────────

def test_missing_map_file_returns_unknown():
    rel, col = resolve_relationship(
        "919812345670@s.whatsapp.net",
        "config/does_not_exist.json",
    )
    assert rel == "unknown"
    assert col == "history_unknown"

def test_broken_json_map_returns_unknown(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{ this is not valid json }", encoding="utf-8")
    rel, col = resolve_relationship("919812345670@s.whatsapp.net", str(p))
    assert rel == "unknown"
    assert col == "history_unknown"

def test_map_missing_default_key(tmp_path):
    """If _default is absent, hard-coded 'unknown' kicks in."""
    data = {"919812345670": "friend"}
    p = tmp_path / "map.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    rel, col = resolve_relationship("919999999999@s.whatsapp.net", str(p))
    assert rel == "unknown"
    assert col == "history_unknown"
