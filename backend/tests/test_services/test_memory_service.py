"""Unit tests for services.memory_service.

Covers the memory lifecycle:
- extract_and_store_memories: parses LLM JSON, stores entries to DB+ChromaDB
- get_contextual_memories: vector retrieval with intimacy gating
- format_memories_for_prompt: deterministic formatting with fidelity tiers
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.security import hash_password
from models.memory_entry import MemoryEntry
from models.user import User
from services import embedding_service, memory_service, vector_store


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("TestPass123!"),
        nickname="MemUser",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _bind_async_session(monkeypatch, engine, mod):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(mod, "async_session", factory, raising=False)


def _stub_llm_with_json(monkeypatch, payload, target_module=memory_service):
    """Replace ``_get_client()`` on target module with a fake whose
    chat.completions.create() returns the given payload as a JSON string."""
    raw = json.dumps(payload)
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=raw))]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=fake_response),
            )
        )
    )
    monkeypatch.setattr(target_module, "_get_client", lambda: fake_client)


# ──────────────────────────────────────────────────────────────────────
# extract_and_store_memories
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_memories_from_message(
    db: AsyncSession, engine, sample_persona, monkeypatch,
):
    """LLM-extracted fragments are persisted as MemoryEntry rows and pushed
    into the vector store."""
    user = await _make_user(db, email="mem_extract@example.com")
    _bind_async_session(monkeypatch, engine, memory_service)

    _stub_llm_with_json(monkeypatch, [
        {"type": "fact", "content": "User's name is Alice."},
        {"type": "emotion", "content": "User feels stressed about exams."},
    ])

    monkeypatch.setattr(
        embedding_service, "get_embeddings",
        AsyncMock(return_value=[[0.1] * 8, [0.2] * 8]),
    )
    add_memory = MagicMock()
    monkeypatch.setattr(vector_store, "add_memory", add_memory)

    await memory_service.extract_and_store_memories(
        user_id=user.id,
        ai_id=sample_persona.id,
        user_message="My name is Alice and I'm stressed.",
        ai_reply="It's okay, Alice.",
    )

    rows = await db.execute(
        select(MemoryEntry).where(MemoryEntry.user_id == user.id)
        .order_by(MemoryEntry.id.asc())
    )
    entries = list(rows.scalars().all())
    assert len(entries) == 2
    assert {e.memory_type for e in entries} == {"fact", "emotion"}
    assert any("Alice" in e.content for e in entries)
    # Each entry should have a non-empty vector_id and a paired ChromaDB add.
    assert all(e.vector_id for e in entries)
    assert add_memory.call_count == 2


@pytest.mark.asyncio
async def test_no_duplicate_memories(
    db: AsyncSession, engine, sample_persona, monkeypatch,
):
    """When the LLM returns an empty array, no MemoryEntry rows are created
    and the vector store is not touched."""
    user = await _make_user(db, email="mem_empty@example.com")
    _bind_async_session(monkeypatch, engine, memory_service)
    _stub_llm_with_json(monkeypatch, [])

    embed_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(embedding_service, "get_embeddings", embed_mock)
    add_memory = MagicMock()
    monkeypatch.setattr(vector_store, "add_memory", add_memory)

    await memory_service.extract_and_store_memories(
        user_id=user.id,
        ai_id=sample_persona.id,
        user_message="hi",
        ai_reply="hello",
    )

    rows = await db.execute(
        select(MemoryEntry).where(MemoryEntry.user_id == user.id)
    )
    assert rows.scalars().first() is None
    add_memory.assert_not_called()
    embed_mock.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────────
# get_contextual_memories
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_contextual_memories_by_relevance(monkeypatch):
    """Vector store results are mapped to memory dicts in the order returned
    by the store (i.e. by relevance / distance)."""
    monkeypatch.setattr(
        embedding_service, "get_embedding",
        AsyncMock(return_value=[0.1] * 8),
    )
    now = datetime.now(timezone.utc)
    fake_results = [
        {
            "content": "User loves jazz piano.",
            "distance": 0.10,
            "metadata": {"memory_type": "fact", "created_at": now.isoformat()},
        },
        {
            "content": "User felt nervous before recitals.",
            "distance": 0.40,
            "metadata": {"memory_type": "emotion", "created_at": now.isoformat()},
        },
    ]
    monkeypatch.setattr(
        vector_store, "query_memories",
        MagicMock(return_value=fake_results),
    )

    memories = await memory_service.get_contextual_memories(
        user_id=1, ai_id=1, query_text="music", intimacy=8.0, top_k=5,
    )

    assert [m["content"] for m in memories] == [
        "User loves jazz piano.",
        "User felt nervous before recitals.",
    ]
    # First entry has lower distance ⇒ higher relevance.
    assert memories[0]["relevance"] > memories[1]["relevance"]


@pytest.mark.asyncio
async def test_memory_confidence_scoring(monkeypatch):
    """relevance is computed as ``1 - distance`` for each result."""
    monkeypatch.setattr(
        embedding_service, "get_embedding",
        AsyncMock(return_value=[0.0] * 8),
    )
    captured = {}

    def fake_query(emb, user_id, ai_id, top_k, memory_types):
        captured["memory_types"] = memory_types
        return [{
            "content": "x",
            "distance": 0.25,
            "metadata": {
                "memory_type": "fact",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        }]

    monkeypatch.setattr(vector_store, "query_memories", fake_query)

    # Low intimacy → only "fact" type should be requested.
    low = await memory_service.get_contextual_memories(
        user_id=1, ai_id=1, query_text="q", intimacy=2.0,
    )
    assert captured["memory_types"] == ["fact"]
    assert low[0]["relevance"] == pytest.approx(0.75)

    # High intimacy → unrestricted (None passed to vector store).
    await memory_service.get_contextual_memories(
        user_id=1, ai_id=1, query_text="q", intimacy=8.0,
    )
    assert captured["memory_types"] is None


@pytest.mark.asyncio
async def test_memory_access_tracking(monkeypatch):
    """Retrieved memories include an age_hours value derived from created_at,
    so downstream callers can attach the right fidelity tier."""
    monkeypatch.setattr(
        embedding_service, "get_embedding",
        AsyncMock(return_value=[0.0] * 8),
    )
    fresh_ts = datetime.now(timezone.utc) - timedelta(hours=2)
    distant_ts = datetime.now(timezone.utc) - timedelta(days=30)
    monkeypatch.setattr(
        vector_store, "query_memories",
        MagicMock(return_value=[
            {
                "content": "fresh memory",
                "distance": 0.1,
                "metadata": {
                    "memory_type": "fact",
                    "created_at": fresh_ts.isoformat(),
                },
            },
            {
                "content": "old memory",
                "distance": 0.2,
                "metadata": {
                    "memory_type": "fact",
                    "created_at": distant_ts.isoformat(),
                },
            },
        ]),
    )

    memories = await memory_service.get_contextual_memories(
        user_id=1, ai_id=1, query_text="q", intimacy=2.0,
    )
    assert memories[0]["age_hours"] < 24
    assert memories[1]["age_hours"] > 24 * 7


# ──────────────────────────────────────────────────────────────────────
# format_memories_for_prompt
# ──────────────────────────────────────────────────────────────────────


def test_format_memories_for_prompt():
    """Empty list returns "" and populated list emits one tagged line per
    memory plus the recall guide block."""
    assert memory_service.format_memories_for_prompt([]) == ""

    rendered = memory_service.format_memories_for_prompt([
        {"type": "fact", "content": "User's name is Alice.", "age_hours": 2.0},
        {"type": "emotion", "content": "User feels nostalgic.", "age_hours": 200.0},
    ])

    assert "Your Memories About This User" in rendered
    assert "[fact] [fresh] User's name is Alice." in rendered
    assert "[emotion] [distant] User feels nostalgic." in rendered
    assert "Memory Recall Rules" in rendered
