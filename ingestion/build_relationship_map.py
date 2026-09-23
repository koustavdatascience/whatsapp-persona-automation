"""
ingestion/build_relationship_map.py
------------------------------------
Reads data/processed_pairs.jsonl, collects every distinct conversation_id,
and merges them into config/contact_relationship_map.json — without ever
overwriting entries you've already classified by hand.

New conversation_ids get the placeholder value "REPLACE_ME" so you know
exactly which ones still need your attention.

Usage:
    python3 ingestion/build_relationship_map.py

Run from the project root.
"""

import json
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
PAIRS_FILE  = Path("data/processed_pairs.jsonl")
MAP_FILE    = Path("config/contact_relationship_map.json")
PLACEHOLDER = "REPLACE_ME"
DEFAULT_KEY = "_default"
DEFAULT_VAL = "unknown"

# ── Step 1: Collect every distinct conversation_id from processed_pairs.jsonl ─
if not PAIRS_FILE.exists():
    print(f"❌  File not found: {PAIRS_FILE}")
    print("    Run ingestion/parse_export.py first to generate it.")
    sys.exit(1)

found_ids: set[str] = set()

with PAIRS_FILE.open(encoding="utf-8") as f:
    for lineno, raw in enumerate(f, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"⚠️   Skipping malformed JSON on line {lineno}: {exc}")
            continue

        cid = record.get("conversation_id", "").strip()
        if cid:
            found_ids.add(cid)

all_ids: list[str] = sorted(found_ids)

# ── Step 2: Load existing map if it exists (never overwrite hand-filled entries)
existing_map: dict[str, str] = {}

if MAP_FILE.exists():
    try:
        with MAP_FILE.open(encoding="utf-8") as f:
            existing_map = json.load(f)
        print(f"📂  Loaded existing map from {MAP_FILE}  ({len(existing_map)} entries)")
    except json.JSONDecodeError as exc:
        print(f"❌  Could not parse {MAP_FILE}: {exc}")
        print("    Fix the JSON by hand or delete the file and re-run.")
        sys.exit(1)
else:
    print(f"📂  No existing map found — will create {MAP_FILE}")

# ── Step 3: Add only NEW conversation_ids with the placeholder value ──────────
new_ids: list[str] = []

for cid in all_ids:
    if cid not in existing_map:
        existing_map[cid] = PLACEHOLDER
        new_ids.append(cid)

# ── Step 4: Ensure the _default key always exists ─────────────────────────────
if DEFAULT_KEY not in existing_map:
    existing_map[DEFAULT_KEY] = DEFAULT_VAL

# ── Step 5: Write back sorted alphabetically, 2-space indentation ─────────────
MAP_FILE.parent.mkdir(parents=True, exist_ok=True)

# Sort: _default first (it starts with '_' so it naturally sorts before letters),
# then all conversation_ids alphabetically.
sorted_map = dict(sorted(existing_map.items()))

with MAP_FILE.open("w", encoding="utf-8") as f:
    json.dump(sorted_map, f, indent=2, ensure_ascii=False)
    f.write("\n")  # trailing newline — good practice for text files

print(f"💾  Written to {MAP_FILE}")

# ── Step 6: Clear, actionable summary ─────────────────────────────────────────
still_placeholder = [k for k, v in sorted_map.items() if v == PLACEHOLDER]

print()
print("══════════════════════════════════════════════")
print("  Relationship Map Summary")
print("══════════════════════════════════════════════")
print(f"  Total conversation_ids in pairs file : {len(all_ids)}")
print(f"  Total entries in map (incl. _default): {len(sorted_map)}")
print(f"  New entries added this run            : {len(new_ids)}")

if new_ids:
    print(f"\n  ✨  Newly added (all set to '{PLACEHOLDER}'):")
    for cid in new_ids:
        print(f"       - {cid}")

if still_placeholder:
    print(f"\n  ⚠️   Still needs your attention ({len(still_placeholder)} entries set to '{PLACEHOLDER}'):")
    for cid in still_placeholder:
        print(f"       → {MAP_FILE}  key: \"{cid}\"")
    print(f"\n  Open {MAP_FILE} and replace each '{PLACEHOLDER}' with the")
    print("  correct relationship tier, e.g.:")
    print('    "partner" | "friends" | "professional" | "unknown"')
else:
    print(f"\n  ✅  All conversation_ids are classified — no '{PLACEHOLDER}' values remain.")

print()
