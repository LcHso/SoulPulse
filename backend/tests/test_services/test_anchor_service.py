"""Unit tests for services.anchor_service.

Covers:
- extract_and_store_anchors (LLM extraction + dedup-aware persistence)
- load_anchors (per-pair retrieval, severity ordering, type filtering)
- increment_hit_counts_bg (association/hit-count updates)
- detect_sentiment (anchor-type categorization for repair flow)
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.security import hash_password
from models.relational_anchor import RelationalAnchor
from models.user import User
from services import anchor_service, embedding_service, vector_store


async def _make_user(db: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("TestPass123!"),
        nickname="AnchorUser",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _bind_async_session(monkeypatch, engine, mod):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(mod, "async_session", factory, raising=False)


# ──────────────────────────────────────────────────────────────────────
# extract_and_store_anchors
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_anchors_from_conversation(
    db: AsyncSession, engine, sample_persona, monkeypatch,
):
    """LLM-extracted anchors are persisted to SQLite and pushed to the anchor
    vector collection (dedup miss path)."""
    user = await _make_user(db, email="anchor_extract@example.com")
    _bind_async_session(monkeypatch, engine, anchor_service)

    payload = json.dumps([
        {"type": "taboo", "content": "User dislikes being compared.", "severity": 4},
        {"type": "fear", "content": "User fears abandonment.", "severity": 5},
    ])
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=fake_response),
            )
        )
    )
    monkeypatch.setattr(anchor_service, "_get_client", lambda: fake_client)
    monkeypatch.setattr(
        embedding_service, "get_embeddings",
        AsyncMock(return_value=[[0.1] * 8, [0.2] * 8]),
    )
    # Dedup lookup: no existing anchor.
    monkeypatch.setattr(
        vector_store, "query_anchor_by_content",
        MagicMock(return_value=None),
    )
    add_anchor = MagicMock()
    monkeypatch.setattr(vector_store, "add_anchor", add_anchor)

    await anchor_service.extract_and_store_anchors(
        user_id=user.id,
        ai_id=sample_persona.id,
        user_message="Don't compare me to others. I get scared.",
        ai_reply="I'm sorry — I won't.",
    )

    rows = await db.execute(
        select(RelationalAnchor).where(RelationalAnchor.user_id == user.id)
    )
    anchors = list(rows.scalars().all())
    assert len(anchors) == 2
    assert {a.anchor_type for a in anchors} == {"taboo", "fear"}
    severities = {a.anchor_type: a.severity for a in anchors}
    assert severities["taboo"] == 4
    assert severities["fear"] == 5
    assert add_anchor.call_count == 2


# ──────────────────────────────────────────────────────────────────────
# load_anchors + type categorization
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_relation_anchors_by_type(
    db: AsyncSession, sample_persona,
):
    """load_anchors returns only the requested user-AI pair, ordered by
    severity desc; callers can then filter by anchor_type."""
    user = await _make_user(db, email="anchor_load@example.com")

    db.add_all([
        RelationalAnchor(
            user_id=user.id, ai_id=sample_persona.id,
            anchor_type="preference", content="Likes jazz",
            severity=2, vector_id="v-pref",
        ),
        RelationalAnchor(
            user_id=user.id, ai_id=sample_persona.id,
            anchor_type="taboo", content="Hates loud noises",
            severity=5, vector_id="v-taboo",
        ),
        RelationalAnchor(
            user_id=user.id, ai_id=sample_persona.id,
            anchor_type="fear", content="Fears the dark",
            severity=4, vector_id="v-fear",
        ),
    ])
    await db.commit()

    anchors = await anchor_service.load_anchors(db, user.id, sample_persona.id)
    assert [a.severity for a in anchors] == [5, 4, 2]

    taboos = [a for a in anchors if a.anchor_type == "taboo"]
    assert len(taboos) == 1 and taboos[0].content == "Hates loud noises"


@pytest.mark.asyncio
async def test_anchor_types_categorized():
    """detect_sentiment maps user phrases to the categories that drive the
    repair-flow branching (negative ⇒ repair section attached)."""
    assert anchor_service.detect_sentiment("我真的很讨厌这个") == "negative"
    assert anchor_service.detect_sentiment("Thank you, this is wonderful!") == "positive"
    assert anchor_service.detect_sentiment("Today is Tuesday.") == "neutral"


# ──────────────────────────────────────────────────────────────────────
# increment_hit_counts_bg (association update path)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_anchor_associations(
    db: AsyncSession, engine, sample_persona, monkeypatch,
):
    """Hitting an anchor through increment_hit_counts_bg bumps hit_count for
    every targeted anchor id."""
    user = await _make_user(db, email="anchor_hits@example.com")

    a1 = RelationalAnchor(
        user_id=user.id, ai_id=sample_persona.id,
        anchor_type="taboo", content="Don't bring up exes",
        severity=4, vector_id="vid-1", hit_count=0,
    )
    a2 = RelationalAnchor(
        user_id=user.id, ai_id=sample_persona.id,
        anchor_type="fear", content="Fear of failing",
        severity=3, vector_id="vid-2", hit_count=2,
    )
    db.add_all([a1, a2])
    await db.commit()
    await db.refresh(a1)
    await db.refresh(a2)

    _bind_async_session(monkeypatch, engine, anchor_service)

    await anchor_service.increment_hit_counts_bg(
        user_id=user.id, ai_id=sample_persona.id, anchor_ids=[a1.id, a2.id],
    )

    refreshed = await db.execute(
        select(RelationalAnchor).where(
            RelationalAnchor.id.in_([a1.id, a2.id])
        )
    )
    by_id = {a.id: a for a in refreshed.scalars().all()}
    # Refresh each row so the underlying counts reflect committed state.
    for anchor in by_id.values():
        await db.refresh(anchor)
    assert by_id[a1.id].hit_count == 1
    assert by_id[a2.id].hit_count == 3
