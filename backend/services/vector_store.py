from __future__ import annotations

from typing import Optional

import chromadb

from core.config import settings

_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None

COLLECTION_NAME = "soulpulse_memories"

# ── Anchor collection ──────────────────────────────────────────
ANCHOR_COLLECTION_NAME = "soulpulse_anchors"
_anchor_collection: chromadb.Collection | None = None


def _get_client() -> chromadb.PersistentClient:
    """Get or create the shared ChromaDB client (lazy singleton)."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    return _client


def get_collection() -> chromadb.Collection:
    """Get or create the ChromaDB collection (lazy singleton)."""
    global _collection
    if _collection is None:
        _collection = _get_client().get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def get_anchor_collection() -> chromadb.Collection:
    """Get or create the ChromaDB anchor collection (lazy singleton)."""
    global _anchor_collection
    if _anchor_collection is None:
        _anchor_collection = _get_client().get_or_create_collection(
            name=ANCHOR_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _anchor_collection


def add_memory(
    vector_id: str,
    embedding: list[float],
    content: str,
    metadata: dict,
) -> None:
    """Insert a memory into ChromaDB with embedding and metadata."""
    collection = get_collection()
    collection.add(
        ids=[vector_id],
        embeddings=[embedding],
        documents=[content],
        metadatas=[metadata],
    )


def query_memories(
    embedding: list[float],
    user_id: int,
    ai_id: int,
    top_k: int = 5,
    memory_types: Optional[list[str]] = None,
) -> list[dict]:
    """
    Query ChromaDB for relevant memories, always filtered by user_id.
    Returns list of {"content": str, "distance": float, "metadata": dict}.
    """
    collection = get_collection()

    # Build where filter -- user_id isolation is mandatory
    where_conditions = [
        {"user_id": str(user_id)},
        {"ai_id": str(ai_id)},
    ]
    if memory_types:
        where_conditions.append({"memory_type": {"$in": memory_types}})

    where_filter = {"$and": where_conditions} if len(where_conditions) > 1 else where_conditions[0]

    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
        where=where_filter,
    )

    memories = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            memories.append({
                "content": doc,
                "distance": results["distances"][0][i] if results["distances"] else 0.0,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
            })
    return memories


# ── Anchor vector operations ───────────────────────────────────

def add_anchor(
    vector_id: str,
    embedding: list[float],
    content: str,
    metadata: dict,
) -> None:
    """Insert an anchor into the anchor ChromaDB collection."""
    collection = get_anchor_collection()
    collection.add(
        ids=[vector_id],
        embeddings=[embedding],
        documents=[content],
        metadatas=[metadata],
    )


def query_anchors(
    embedding: list[float],
    user_id: int,
    ai_id: int,
    top_k: int = 20,
) -> list[dict]:
    """Query the anchor collection for anchors relevant to the given context.

    Returns list of {"content", "distance", "metadata"} dicts.
    Always filtered by user_id + ai_id for multi-tenant isolation.
    """
    collection = get_anchor_collection()

    where_filter = {
        "$and": [
            {"user_id": str(user_id)},
            {"ai_id": str(ai_id)},
        ]
    }

    try:
        results = collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where=where_filter,
        )
    except Exception:
        # Collection may be empty → no results
        return []

    anchors = []
    if results and results["documents"] and results["documents"][0]:
        for i, doc in enumerate(results["documents"][0]):
            anchors.append({
                "content": doc,
                "distance": results["distances"][0][i] if results["distances"] else 0.0,
                "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
            })
    return anchors


def query_anchor_by_content(
    embedding: list[float],
    user_id: int,
    ai_id: int,
) -> dict | None:
    """Find the single closest anchor for dedup checking.

    Returns the closest match dict or None if collection is empty.
    """
    results = query_anchors(embedding, user_id, ai_id, top_k=1)
    return results[0] if results else None
