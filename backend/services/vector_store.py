from __future__ import annotations

from typing import Optional

import chromadb

from core.config import settings

_client: chromadb.PersistentClient | None = None
_collection: chromadb.Collection | None = None

COLLECTION_NAME = "soulpulse_memories"


def get_collection() -> chromadb.Collection:
    """Get or create the ChromaDB collection (lazy singleton)."""
    global _client, _collection
    if _collection is None:
        _client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        _collection = _client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


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
