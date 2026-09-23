"""
ingestion/validate_relationship_map.py
----------------------------------------
Pre-flight safety check: confirms that every conversation_id in
data/processed_pairs.jsonl has a fully-classified (non-"REPLACE_ME") entry in
config/contact_relationship_map.json.

Exits with code 0 if everything is classified.
Exits with code 1 and a clear list of problems if anything is missing or
still set to the placeholder — so this can be wired into any pipeline as a
gate before the embedding/indexing step.

Usage:
    python3 ingestion/validate_relationship_map.py

Run from the project root.
"""

import json
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
PAIRS_FILE  = Path("data/processed_pairs.jsonl")
MAP_FILE    = Path("config/contact_relationship_map.json")
PLACEHOLDER = "REPLACE_ME"

errors: list[str] = []

# ── Check that required files exist ───────────────────────────────────────────
if not PAIRS_FILE.exists():
    print(f"❌  Pairs file not found: {PAIRS_FILE}")
    print("    Run ingestion/parse_export.py first.")
    sys.exit(1)

if not MAP_FILE.exists():
    print(f"❌  Relationship map not found: {MAP_FILE}")
    print("    Run ingestion/build_relationship_map.py first.")
    sys.exit(1)

# ── Load the relationship map ─────────────────────────────────────────────────
try:
    with MAP_FILE.open(encoding="utf-8") as f:
        rel_map: dict[str, str] = json.load(f)
except json.JSONDecodeError as exc:
    print(f"❌  Could not parse {MAP_FILE}: {exc}")
    sys.exit(1)

# ── Collect distinct conversation_ids from pairs file ─────────────────────────
found_ids: set[str] = set()

with PAIRS_FILE.open(encoding="utf-8") as f:
    for lineno, raw in enumerate(f, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError:
            # Malformed lines are a parse_export concern, not ours — skip silently
            continue
        cid = record.get("conversation_id", "").strip()
        if cid:
            found_ids.add(cid)

all_ids = sorted(found_ids)

# ── Validate each conversation_id ─────────────────────────────────────────────
missing:     list[str] = []   # not in the map at all
placeholder: list[str] = []   # in the map but still set to REPLACE_ME

for cid in all_ids:
    if cid not in rel_map:
        missing.append(cid)
    elif rel_map[cid] == PLACEHOLDER:
        placeholder.append(cid)

# ── Report ────────────────────────────────────────────────────────────────────
print()
print("══════════════════════════════════════════════")
print("  Relationship Map Validation")
print("══════════════════════════════════════════════")
print(f"  Pairs file         : {PAIRS_FILE}")
print(f"  Map file           : {MAP_FILE}")
print(f"  Conversation IDs   : {len(all_ids)}")

if missing:
    print(f"\n  ❌  MISSING from map ({len(missing)}):")
    for cid in missing:
        print(f"       - \"{cid}\"  ← not in {MAP_FILE}")
    print(f"\n  Fix: run  python3 ingestion/build_relationship_map.py")
    print(       "       then open the map and fill in the value.")

if placeholder:
    print(f"\n  ❌  Still set to '{PLACEHOLDER}' ({len(placeholder)}):")
    for cid in placeholder:
        print(f"       - \"{cid}\"  ← open {MAP_FILE} and replace '{PLACEHOLDER}'")
    print(f"\n  Valid tiers: partner | friends | professional | unknown")
    print(  "  (or any custom string that matches your persona tier names)")

if not missing and not placeholder:
    print(f"\n  ✅  All {len(all_ids)} conversation_id(s) are fully classified.")
    print("  Safe to proceed with the embedding/indexing step.")
    print()
    sys.exit(0)

# At least one problem — exit non-zero so CI / pipeline scripts can catch it
print()
total_problems = len(missing) + len(placeholder)
print(f"  ⛔  {total_problems} problem(s) found. Fix them before running the indexer.")
print()
sys.exit(1)
