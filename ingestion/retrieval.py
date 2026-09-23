"""
ingestion/retrieval.py
-----------------------
Clean, importable RAG retrieval module for the WLM History Brain.

The embedding model and ChromaDB client are loaded once at module import
time — repeated calls to retrieve_similar() reuse them without reloading.

Public API
----------
    retrieve_similar(relationship, incoming_message, k=3) -> list[dict]

Each returned dict has the shape:
    {
        "their_message": str,   # the past incoming message
        "my_reply":      str,   # Koustav's past reply  (use this as RAG context)
        "distance":      float, # cosine distance — lower = more similar
    }

Returns an empty list if the collection doesn't exist or has zero documents.
Raises only on genuine connection failures (Chroma server unreachable).
"""

import chromadb
from sentence_transformers import SentenceTransformer

# ── Config ────────────────────────────────────────────────────────────────────
EMBED_MODEL = "paraphrase-multilingual-mpnet-base-v2"
CHROMA_HOST = "localhost"
CHROMA_PORT = 8000

RELATIONSHIP_TO_COLLECTION: dict[str, str] = {
    "family":       "history_family",
    "friend":       "history_friend",
    "professional": "history_professional",
    "unknown":      "history_unknown",
}

# ── Module-level singletons — loaded once, reused on every call ───────────────
# SentenceTransformer loads ~1 GB of weights; reloading per-call would be
# catastrophically slow in a live pipeline.
_model: SentenceTransformer = SentenceTransformer(EMBED_MODEL)

# HttpClient raises immediately if the server is unreachable, which is the
# correct behaviour — callers should not silently proceed without a DB.
_chroma: chromadb.HttpClient = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


# ── Public function ───────────────────────────────────────────────────────────

def retrieve_similar(
    relationship: str,
    incoming_message: str,
    k: int = 3,
) -> list[dict]:
    """
    Find the k most similar past (their_message → my_reply) pairs for the
    given relationship tier.

    Parameters
    ----------
    relationship      : tier string — "family", "friend", "professional",
                        "unknown", or any key in RELATIONSHIP_TO_COLLECTION.
    incoming_message  : the new message to embed and search with.
    k                 : number of results to return (default 3).

    Returns
    -------
    list[dict]  — each dict has keys "their_message", "my_reply", "distance".
                  Empty list if the collection is missing or empty.

    Raises
    ------
    Exception   — only on a genuine ChromaDB connection failure, so the
                  caller can decide whether to abort or fall back to
                  persona-only generation.
    """
    # Resolve relationship → collection name; fall back to unknown
    col_name = RELATIONSHIP_TO_COLLECTION.get(
        relationship.lower(),
        RELATIONSHIP_TO_COLLECTION["unknown"],
    )

    # get_or_create is safe to call repeatedly — no-op if already exists
    collection = _chroma.get_or_create_collection(col_name)

    # Guard: empty collection — return [] rather than raising
    doc_count = collection.count()
    if doc_count == 0:
        return []

    # Embed the incoming message with the shared model
    query_embedding = _model.encode(
        incoming_message,
        convert_to_tensor=False,
    ).tolist()

    # Query — don't ask for more results than the collection holds
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(k, doc_count),
        include=["documents", "metadatas", "distances"],
    )

    # Unpack and reshape into clean dicts
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    return [
        {
            "their_message": doc,
            "my_reply":      meta.get("my_reply", ""),
            "distance":      dist,
        }
        for doc, meta, dist in zip(documents, metadatas, distances)
    ]
