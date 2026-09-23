"""
ingestion/retrieval_demo.py
----------------------------
CLI tool for testing ChromaDB RAG retrieval against all relationship
collections. Shows top-3 similar past pairs per query with distance scores
and a sanity check on result ordering.

Retrieval logic lives in ingestion/retrieval.py — this file is the
human-readable CLI wrapper around it.

Usage examples:
    # Run all 4 relationships with built-in sample queries
    python3 ingestion/retrieval_demo.py

    # Test one relationship only
    python3 ingestion/retrieval_demo.py --relationship friend

    # Provide your own query
    python3 ingestion/retrieval_demo.py --relationship professional --query "Any update on the draft?"

    # Multiple words in query — quote them
    python3 ingestion/retrieval_demo.py --relationship family --query "Good morning, kothay achis?"

Run from the project root.
"""

import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingestion.retrieval import retrieve_similar, RELATIONSHIP_TO_COLLECTION

# Built-in sample queries — chosen to match the tone and language of each tier
DEFAULT_QUERIES: dict[str, list[str]] = {
    "family": [
        "Good morning, kothay achis?",          # Bengalish casual check-in
        "Porte bosh, exam kobe?",               # study / daily life
        "Bari ashbi kobe?",                     # coming home question
    ],
    "friend": [
        "Valorant khelbi akhon? lobby bana",    # gaming coordination
        "Bhai free achish? adda debo",            # casual hangout
        "Kire, ki korchish ekhon?",               # generic banter
    ],
    "professional": [
        "Hey Koustav, any update on the video draft?",      # work status
        "Can you send the final version by tonight?",       # deadline
        "I wanted to discuss the social media post layout", # project detail
    ],
    "unknown": [
        "Hi, got your number from the group",   # stranger intro
        "Hello, are you available for a project?",
        "Is this Koustav? I needed some help",
    ],
}

ALL_RELATIONSHIPS = list(RELATIONSHIP_TO_COLLECTION.keys())
TOP_K = 3


# ── Argument parsing ──────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test ChromaDB RAG retrieval for WLM relationship collections.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--relationship",
        choices=ALL_RELATIONSHIPS,
        default=None,
        help=(
            "Which relationship collection to query. "
            "Omit to run all four: family, friend, professional, unknown."
        ),
    )
    parser.add_argument(
        "--query",
        default=None,
        help=(
            "Custom query string to search with. "
            "Omit to use the built-in sample queries for the chosen relationship."
        ),
    )
    return parser.parse_args()


# ── Sanity check helper ───────────────────────────────────────────────────────
def is_monotonically_increasing(values: list[float]) -> bool:
    """True if each value is >= the previous one (expected for distance scores)."""
    return all(values[i] <= values[i + 1] for i in range(len(values) - 1))


# ── Display helpers ───────────────────────────────────────────────────────────
HEAVY_LINE = "═" * 56
THIN_LINE  = "─" * 56
RESULT_SEP = "  " + "·" * 52


def print_header(text: str) -> None:
    print(f"\n{HEAVY_LINE}")
    print(f"  {text}")
    print(HEAVY_LINE)


def print_result(rank: int, their_message: str, my_reply: str, distance: float) -> None:
    """Pretty-prints one retrieval result."""
    def clip(s: str, n: int = 120) -> str:
        s = s.replace("\n", " ↵ ")
        return s[:n] + "…" if len(s) > n else s

    print(f"\n  #{rank}  distance: {distance:.4f}")
    print(f"  {'─'*52}")
    print(f"  📩 Incoming : {clip(their_message)}")
    print(f"  💬 My reply : {clip(my_reply)}")


# ── Core query function ───────────────────────────────────────────────────────
def run_queries(
    relationship: str,
    queries: list[str],
) -> None:
    """
    Calls retrieve_similar() for each query, prints results neatly,
    and prints a per-relationship sanity check on distance ordering.
    """
    col_name = RELATIONSHIP_TO_COLLECTION.get(relationship, f"history_{relationship}")

    print_header(f"RELATIONSHIP: {relationship.upper()}  │  collection: {col_name}")

    # Track distance lists across queries for the sanity check
    all_distance_lists: list[list[float]] = []

    for q_idx, query in enumerate(queries, start=1):
        print(f"\n  ┌─ Query {q_idx}/{len(queries)} {'─'*40}")
        print(f"  │  \"{query}\"")
        print(f"  └{'─'*52}")

        # retrieve_similar returns [] for empty/missing collections — no crash
        hits = retrieve_similar(relationship, query, k=TOP_K)

        if not hits:
            print(f"\n  ⚠️   history_{relationship} is empty — skipping.")
            print(f"       Run python3 ingestion/embed_to_chroma.py to populate it.")
            return

        distances: list[float] = []
        for rank, hit in enumerate(hits, start=1):
            print_result(rank, hit["their_message"], hit["my_reply"], hit["distance"])
            distances.append(hit["distance"])

        print(f"\n  {THIN_LINE}")
        all_distance_lists.append(distances)

    # ── Sanity check: distances should increase (closest result first) ────────
    print(f"\n  📊 Sanity check for '{relationship}':")
    any_issue = False
    for q_idx, distances in enumerate(all_distance_lists, start=1):
        ok = is_monotonically_increasing(distances)
        status = "✅ distances increasing (good)" if ok else "⚠️  distances NOT monotonic — worth a second look"
        rounded = [f"{d:.4f}" for d in distances]
        print(f"     Query {q_idx}: {rounded}  →  {status}")
        if not ok:
            any_issue = True

    if not any_issue:
        print(f"  ✅  All queries for '{relationship}' returned results in expected order.")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    args = parse_args()

    # Decide which relationships to test
    relationships_to_test: list[str] = (
        [args.relationship] if args.relationship else ALL_RELATIONSHIPS
    )

    # Decide which queries to use — custom or built-in
    custom_query: str | None = args.query

    # Model and Chroma client are loaded at module import time in retrieval.py
    # Nothing to initialise here — just run the queries.
    print(f"\n{HEAVY_LINE}")
    print("  WLM Retrieval Demo")
    print(HEAVY_LINE)

    # ── Run queries per relationship ──────────────────────────────────────────
    for rel in relationships_to_test:
        queries = [custom_query] if custom_query else DEFAULT_QUERIES[rel]
        run_queries(rel, queries)

    print(f"\n{HEAVY_LINE}")
    print("  DONE")
    print(HEAVY_LINE)
    print()


if __name__ == "__main__":
    main()
