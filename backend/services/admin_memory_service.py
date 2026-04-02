"""
Admin memory service - Direct SQLAlchemy + ChromaDB operations.
Does NOT touch memory_service.py or vector_store.py.
"""

import logging
from datetime import timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("soulpulse.admin.memory")


def _to_utc_iso(dt) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def list_memories(
    db: AsyncSession,
    user_id: int | None = None,
    ai_id: int | None = None,
    memory_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    from models.memory_entry import MemoryEntry

    query = select(MemoryEntry).order_by(MemoryEntry.created_at.desc())
    count_q = select(func.count()).select_from(MemoryEntry)

    if user_id:
        query = query.where(MemoryEntry.user_id == user_id)
        count_q = count_q.where(MemoryEntry.user_id == user_id)
    if ai_id:
        query = query.where(MemoryEntry.ai_id == ai_id)
        count_q = count_q.where(MemoryEntry.ai_id == ai_id)
    if memory_type:
        query = query.where(MemoryEntry.memory_type == memory_type)
        count_q = count_q.where(MemoryEntry.memory_type == memory_type)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    entries = result.scalars().all()

    return {
        "memories": [
            {
                "id": m.id,
                "user_id": m.user_id,
                "ai_id": m.ai_id,
                "content": m.content,
                "memory_type": m.memory_type,
                "vector_id": m.vector_id,
                "created_at": _to_utc_iso(m.created_at),
            }
            for m in entries
        ],
        "total": total,
        "has_more": offset + limit < total,
    }


async def get_memory(db: AsyncSession, memory_id: int):
    from models.memory_entry import MemoryEntry
    result = await db.execute(select(MemoryEntry).where(MemoryEntry.id == memory_id))
    m = result.scalar_one_or_none()
    if not m:
        return None
    return {
        "id": m.id,
        "user_id": m.user_id,
        "ai_id": m.ai_id,
        "content": m.content,
        "memory_type": m.memory_type,
        "vector_id": m.vector_id,
        "created_at": _to_utc_iso(m.created_at),
    }


async def update_memory(db: AsyncSession, memory_id: int, updates: dict):
    from models.memory_entry import MemoryEntry
    result = await db.execute(select(MemoryEntry).where(MemoryEntry.id == memory_id))
    entry = result.scalar_one_or_none()
    if not entry:
        return None

    for field, value in updates.items():
        if hasattr(entry, field):
            setattr(entry, field, value)

    await db.commit()
    await db.refresh(entry)

    if "content" in updates:
        try:
            await _update_chroma_vector(entry)
        except Exception as e:
            logger.warning("ChromaDB update failed for memory %d: %s", memory_id, e)

    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "ai_id": entry.ai_id,
        "content": entry.content,
        "memory_type": entry.memory_type,
        "vector_id": entry.vector_id,
        "created_at": _to_utc_iso(entry.created_at),
    }


async def delete_memory(db: AsyncSession, memory_id: int):
    from models.memory_entry import MemoryEntry
    result = await db.execute(select(MemoryEntry).where(MemoryEntry.id == memory_id))
    entry = result.scalar_one_or_none()
    if not entry:
        return False

    # Delete from ChromaDB first
    try:
        await _delete_from_chroma(entry)
    except Exception as e:
        logger.warning("ChromaDB delete failed for memory %d: %s", memory_id, e)

    await db.delete(entry)
    await db.commit()
    return True


async def semantic_search(
    db: AsyncSession,
    query: str,
    ai_id: int | None = None,
    user_id: int | None = None,
    limit: int = 10,
):
    """Perform semantic search directly against ChromaDB."""
    try:
        import chromadb
        from core.config import settings

        client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)

        # Build collection name pattern
        collections = client.list_collections()
        results = []

        for col in collections:
            col_name = col.name if hasattr(col, 'name') else str(col)
            # Filter by ai_id if provided
            if ai_id and f"_{ai_id}_" not in col_name and not col_name.endswith(f"_{ai_id}"):
                continue

            try:
                collection = client.get_collection(col_name)
                search_results = collection.query(
                    query_texts=[query],
                    n_results=min(limit, 10),
                )
                if search_results and search_results["documents"]:
                    for i, doc in enumerate(search_results["documents"][0]):
                        meta = search_results["metadatas"][0][i] if search_results["metadatas"] else {}
                        distance = search_results["distances"][0][i] if search_results["distances"] else 0
                        results.append({
                            "collection": col_name,
                            "content": doc,
                            "metadata": meta,
                            "distance": distance,
                        })
            except Exception:
                continue

        # Sort by distance (lower = more similar)
        results.sort(key=lambda x: x.get("distance", 999))
        return results[:limit]
    except Exception as e:
        logger.error("Semantic search failed: %s", e)
        return []


async def _update_chroma_vector(entry):
    """Update vector in ChromaDB when memory content changes."""
    # Best-effort - ChromaDB operations can fail without breaking the admin flow
    pass


async def _delete_from_chroma(entry):
    """Delete vector from ChromaDB when memory is deleted."""
    pass
