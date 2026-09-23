"""
ingestion/embed_to_chroma.py
-----------------------------
Embeds every processed message pair into ChromaDB, organised into one
collection per relationship class.

Pre-requisites:
  • Chroma server running on localhost:8000
      → pwsh scripts/setup_session_2_2.ps1   (or the .sh on Mac/Linux)
  • All conversation_ids classified (no REPLACE_ME values)
      → python3 ingestion/validate_relationship_map.py

Usage:
    python3 ingestion/embed_to_chroma.py

Run from the project root.
"""

import hashlib
import json
import sys
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

# ── Config ────────────────────────────────────────────────────────────────────
PAIRS_FILE   = Path("data/processed_pairs.jsonl")
MAP_FILE     = Path("config/contact_relationship_map.json")
EMBED_MODEL  = "paraphrase-multilingual-mpnet-base-v2"
CHROMA_HOST  = "localhost"
CHROMA_PORT  = 8000

# Collection names — one per relationship class.
# The key is the tier value stored in the relationship map;
# the value is the ChromaDB collection name.
COLLECTION_MAP: dict[str, str] = {
    "partner":      "history_family",     # intimate / partner maps to family-class
    "family":       "history_family",
    "friends":      "history_friend",
    "friend":       "history_friend",
    "professional": "history_professional",
    "unknown":      "history_unknown",
}
# All collections we will guarantee exist, even if empty
ALL_COLLECTIONS = {
    "history_family",
    "history_friend",
    "history_professional",
    "history_unknown",
}

PROGRESS_EVERY = 50   # print a progress line every N pairs


# ── Helpers ───────────────────────────────────────────────────────────────────

def stable_id(conversation_id: str, timestamp: str, index: int) -> str:
    """
    Deterministic document ID so re-running never creates duplicates.
    We hash (conversation_id + timestamp + index) with MD5 — collisions are
    astronomically unlikely for this data volume, and MD5 is fast.
    """
    raw = f"{conversation_id}|{timestamp}|{index}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def collection_for_tier(tier: str) -> str:
    """Maps a relationship tier string to the correct collection name."""
    return COLLECTION_MAP.get(tier.lower(), "history_unknown")


# ── Step 1: Load pairs ────────────────────────────────────────────────────────
print()
print("══════════════════════════════════════════════")
print(" STEP 1 — Loading pairs")
print("══════════════════════════════════════════════")

if not PAIRS_FILE.exists():
    print(f"❌  Pairs file not found: {PAIRS_FILE}")
    print("    Run ingestion/parse_export.py first.")
    sys.exit(1)

pairs: list[dict] = []
with PAIRS_FILE.open(encoding="utf-8") as f:
    for lineno, raw in enumerate(f, start=1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            pairs.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            print(f"  ⚠️   Skipping malformed line {lineno}: {exc}")

print(f"  ✅  Loaded {len(pairs)} pairs from {PAIRS_FILE}")

# ── Step 2: Load relationship map ─────────────────────────────────────────────
print()
print("══════════════════════════════════════════════")
print(" STEP 2 — Loading relationship map")
print("══════════════════════════════════════════════")

if not MAP_FILE.exists():
    print(f"❌  Relationship map not found: {MAP_FILE}")
    print("    Run ingestion/build_relationship_map.py first.")
    sys.exit(1)

with MAP_FILE.open(encoding="utf-8") as f:
    rel_map: dict[str, str] = json.load(f)

default_tier = rel_map.get("_default", "unknown")
print(f"  ✅  Loaded map with {len(rel_map)} entries  (default tier: '{default_tier}')")

# Tag each pair with its relationship tier
for pair in pairs:
    cid  = pair.get("conversation_id", "")
    tier = rel_map.get(cid, default_tier)
    pair["_tier"]       = tier
    pair["_collection"] = collection_for_tier(tier)

# ── Step 3: Load the embedding model (once) ───────────────────────────────────
print()
print("══════════════════════════════════════════════")
print(" STEP 3 — Loading embedding model")
print("══════════════════════════════════════════════")
print(f"  📦  Model: {EMBED_MODEL}")
print("  (First run downloads ~1 GB — subsequent runs use the local cache)")

model = SentenceTransformer(EMBED_MODEL)
print("  ✅  Model loaded.")

# ── Step 4: Connect to ChromaDB ───────────────────────────────────────────────
print()
print("══════════════════════════════════════════════")
print(" STEP 4 — Connecting to ChromaDB")
print("══════════════════════════════════════════════")

try:
    chroma = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    # heartbeat() raises if the server is unreachable
    chroma.heartbeat()
    print(f"  ✅  Connected to Chroma at {CHROMA_HOST}:{CHROMA_PORT}")
except Exception as exc:
    print(f"  ❌  Cannot reach Chroma server: {exc}")
    print(f"      Make sure it's running:  pwsh scripts/setup_session_2_2.ps1")
    sys.exit(1)

# ── Step 5: Create (or get) one collection per relationship class ──────────────
print()
print("══════════════════════════════════════════════")
print(" STEP 5 — Creating / verifying collections")
print("══════════════════════════════════════════════")

# get_or_create_collection is idempotent — safe to call on every run.
collections: dict[str, chromadb.Collection] = {}
for col_name in sorted(ALL_COLLECTIONS):
    col = chroma.get_or_create_collection(
        name=col_name,
        # cosine distance is standard for sentence-transformer embeddings
        metadata={"hnsw:space": "cosine"},
    )
    collections[col_name] = col
    print(f"  ✅  {col_name}  ({col.count()} existing docs)")

# ── Step 6: Embed and upsert ──────────────────────────────────────────────────
print()
print("══════════════════════════════════════════════")
print(" STEP 6 — Embedding & upserting pairs")
print("══════════════════════════════════════════════")

# Group pairs by collection so we can batch-embed per collection —
# this is more memory-efficient than encoding all at once.
from collections import defaultdict
groups: dict[str, list[tuple[int, dict]]] = defaultdict(list)
for idx, pair in enumerate(pairs):
    groups[pair["_collection"]].append((idx, pair))

counts: dict[str, int] = {name: 0 for name in ALL_COLLECTIONS}

for col_name, items in groups.items():
    col = collections[col_name]
    print(f"\n  📂  {col_name}  ({len(items)} pairs to upsert)")

    # Pull out the texts we need to embed for this collection
    texts      = [item[1]["their_message"] for item in items]
    global_idx = [item[0] for item in items]
    item_pairs = [item[1] for item in items]

    # Encode the whole batch at once for this collection
    # show_progress_bar gives a tqdm bar during encoding
    # convert_to_tensor=False returns a numpy array; .tolist() gives plain Python
    # lists that ChromaDB's upsert expects. (convert_to_list was removed in v6+)
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=True,
        convert_to_tensor=False,
    ).tolist()

    # Build upsert payload and send in chunks (ChromaDB recommends ≤5000 at once)
    CHUNK = 500
    for start in range(0, len(items), CHUNK):
        end   = min(start + CHUNK, len(items))
        chunk_items      = item_pairs[start:end]
        chunk_embeddings = embeddings[start:end]

        ids        = []
        metas      = []
        documents  = []

        for i, pair in enumerate(chunk_items):
            doc_id = stable_id(
                pair.get("conversation_id", ""),
                pair.get("timestamp", ""),
                global_idx[start + i],
            )
            ids.append(doc_id)
            documents.append(pair["their_message"])
            metas.append({
                "my_reply":        pair.get("my_reply", ""),
                "timestamp":       pair.get("timestamp", ""),
                "conversation_id": pair.get("conversation_id", ""),
                "relationship":    pair.get("_tier", "unknown"),
            })

            # Progress indicator — print every PROGRESS_EVERY pairs overall
            overall = global_idx[start + i] + 1
            if overall % PROGRESS_EVERY == 0:
                print(f"    … {overall}/{len(pairs)} pairs processed")

        col.upsert(
            ids=ids,
            embeddings=chunk_embeddings,
            documents=documents,
            metadatas=metas,
        )
        counts[col_name] += len(ids)

# ── Step 7: Summary ───────────────────────────────────────────────────────────
print()
print("══════════════════════════════════════════════")
print(" ✅  EMBEDDING COMPLETE — Summary")
print("══════════════════════════════════════════════")

total_upserted = 0
for col_name in sorted(ALL_COLLECTIONS):
    n = counts[col_name]
    total_upserted += n
    # Fetch the live count from Chroma to confirm what's actually stored
    live = collections[col_name].count()
    flag = "  ⚠️  EMPTY" if live == 0 else ""
    print(f"  {col_name:<28}  upserted: {n:>4}   total in DB: {live:>4}{flag}")

print(f"\n  Total pairs upserted this run : {total_upserted}")
print(f"  Total pairs in file           : {len(pairs)}")

# Warn on any completely empty collection
empty = [n for n in ALL_COLLECTIONS if collections[n].count() == 0]
if empty:
    print()
    print("  ⚠️   The following collections are empty — check your relationship map:")
    for n in sorted(empty):
        print(f"       - {n}")
else:
    print()
    print("  ✅  All collections have data. Ready for RAG retrieval.")

print()
