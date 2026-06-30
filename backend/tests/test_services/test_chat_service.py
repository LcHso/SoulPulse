"""Unit tests for services.chat_service.

These exercise the service-layer functions directly (not via HTTP):
- persist_message / get_history (cursor pagination, message_type)
- build_context_window (summary inclusion + recent message cap)
- maybe_generate_summary (rolling summary trigger threshold)
- handle_user_message (orchestration: persistence + context assembly)
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.security import hash_password
from models.chat_message import ChatMessage
from models.chat_summary import ChatSummary
from models.user import User
from services import chat_service


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _make_user(db: AsyncSession, email: str = "chat_unit@example.com") -> User:
    user = User(
        email=email,
        hashed_password=hash_password("TestPass123!"),
        nickname="ChatUnitUser",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _patch_async_session_to_engine(monkeypatch, engine, *modules):
    """Bind core.database.async_session (as imported into target modules) to
    a session factory backed by the test in-memory engine."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    for mod in modules:
        monkeypatch.setattr(mod, "async_session", factory, raising=False)
    return factory


# ──────────────────────────────────────────────────────────────────────
# build_context_window
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_context_window_includes_summary(db: AsyncSession, sample_persona):
    """When a ChatSummary exists for the conversation, build_context_window
    returns its content as the summary string."""
    user = await _make_user(db, email="ctx_summary@example.com")

    db.add(ChatSummary(
        user_id=user.id,
        ai_id=sample_persona.id,
        content="Earlier they discussed travel plans and the user's anxiety.",
        message_range_start=1,
        message_range_end=5,
    ))
    await db.commit()

    summary, recent = await chat_service.build_context_window(
        db, user.id, sample_persona.id,
    )

    assert "travel plans" in summary
    assert isinstance(recent, list)


@pytest.mark.asyncio
async def test_build_context_window_token_limit(db: AsyncSession, sample_persona):
    """build_context_window caps recent messages to _CONTEXT_RECENT_COUNT (5)."""
    user = await _make_user(db, email="ctx_limit@example.com")

    # Insert 8 messages — only the most recent 5 should be returned.
    for i in range(8):
        db.add(ChatMessage(
            user_id=user.id,
            ai_id=sample_persona.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"msg-{i}",
            message_type="chat",
            delivered=1,
        ))
    await db.commit()

    _summary, recent = await chat_service.build_context_window(
        db, user.id, sample_persona.id,
    )

    assert len(recent) == chat_service._CONTEXT_RECENT_COUNT == 5
    # Oldest of the returned slice is msg-3 (because 8 - 5 = 3).
    assert recent[0]["content"] == "msg-3"
    assert recent[-1]["content"] == "msg-7"


# ──────────────────────────────────────────────────────────────────────
# get_history (cursor pagination) + message_type round-trip
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_history_cursor_correct(db: AsyncSession, sample_persona):
    """get_history with before_id returns only messages older than the cursor,
    in ascending order, capped by limit."""
    user = await _make_user(db, email="history_cursor@example.com")

    inserted: list[ChatMessage] = []
    for i in range(6):
        m = ChatMessage(
            user_id=user.id,
            ai_id=sample_persona.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"history-{i}",
            message_type="chat",
            delivered=1,
        )
        db.add(m)
        inserted.append(m)
    await db.commit()
    for m in inserted:
        await db.refresh(m)

    cursor_id = inserted[4].id  # before the 5th message
    older = await chat_service.get_history(
        db, user.id, sample_persona.id, limit=10, before_id=cursor_id,
    )

    # Should return exactly the first 4 messages, oldest first.
    assert [m.content for m in older] == [
        "history-0", "history-1", "history-2", "history-3",
    ]
    assert all(m.id < cursor_id for m in older)


@pytest.mark.asyncio
async def test_message_type_detection(db: AsyncSession, sample_persona):
    """persist_message round-trips different message_types correctly, and
    get_undelivered_dms only returns proactive_dm rows with delivered=0."""
    user = await _make_user(db, email="msg_type@example.com")

    chat_msg = await chat_service.persist_message(
        db, user.id, sample_persona.id, "user", "hello",
        message_type="chat",
    )
    proactive_msg = await chat_service.persist_message(
        db, user.id, sample_persona.id, "assistant", "I miss you",
        message_type="proactive_dm",
        delivered=0,
        event="long_silence",
    )
    await db.commit()

    assert chat_msg.message_type == "chat"
    assert proactive_msg.message_type == "proactive_dm"
    assert proactive_msg.delivered == 0
    assert proactive_msg.event == "long_silence"

    pending = await chat_service.get_undelivered_dms(
        db, user.id, sample_persona.id,
    )
    assert len(pending) == 1
    assert pending[0].id == proactive_msg.id


# ──────────────────────────────────────────────────────────────────────
# maybe_generate_summary
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_maybe_generate_summary_triggers(
    db: AsyncSession, engine, sample_persona, monkeypatch,
):
    """When unsummarized message count >= threshold, maybe_generate_summary
    creates a ChatSummary row covering the new turns."""
    user = await _make_user(db, email="summary_trigger@example.com")

    # Seed exactly _SUMMARY_THRESHOLD messages so the trigger fires.
    threshold = chat_service._SUMMARY_THRESHOLD
    for i in range(threshold):
        db.add(ChatMessage(
            user_id=user.id,
            ai_id=sample_persona.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"summarize-{i}",
            message_type="chat",
            delivered=1,
        ))
    await db.commit()

    # Bind chat_service.async_session to the test engine so the background
    # function operates on the same in-memory database.
    _patch_async_session_to_engine(monkeypatch, engine, chat_service)

    # Stub the LLM client used inside maybe_generate_summary.
    fake_response = SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="Generated rolling summary text.")
        )]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=AsyncMock(return_value=fake_response),
            )
        )
    )
    monkeypatch.setattr(chat_service, "_get_client", lambda: fake_client)

    await chat_service.maybe_generate_summary(user.id, sample_persona.id)

    # Verify a ChatSummary now exists for the conversation.
    result = await db.execute(
        select(ChatSummary).where(
            ChatSummary.user_id == user.id,
            ChatSummary.ai_id == sample_persona.id,
        )
    )
    summary = result.scalar_one_or_none()
    assert summary is not None
    assert summary.content == "Generated rolling summary text."
    assert summary.message_range_start <= summary.message_range_end


# ──────────────────────────────────────────────────────────────────────
# handle_user_message (orchestration)
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def _patched_orchestration(monkeypatch, engine):
    """Mock all heavy collaborators of handle_user_message so it runs purely
    against the test DB without external services or background DB writes."""
    # 1. AI reply (chat_with_ai is imported by name into chat_service).
    fake_chat = AsyncMock(return_value="Mocked AI reply.")
    monkeypatch.setattr(chat_service, "chat_with_ai", fake_chat)

    # 2. Embedding for memory/anchor lookup.
    from services import embedding_service
    monkeypatch.setattr(
        embedding_service, "get_embedding",
        AsyncMock(return_value=[0.0] * 8),
    )

    # 3. Memory & anchor reads return empty so no LLM/vector ops.
    from services import memory_service, anchor_service
    monkeypatch.setattr(
        memory_service, "get_contextual_memories",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        memory_service, "format_memories_for_prompt",
        MagicMock(return_value=""),
    )
    monkeypatch.setattr(
        anchor_service, "load_anchors",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        anchor_service, "detect_active_anchors",
        AsyncMock(return_value=[]),
    )

    # 4. Fire-and-forget background tasks: replace with no-op coroutines so
    #    they don't touch the production DB / hit Aliyun.
    monkeypatch.setattr(
        memory_service, "extract_and_store_memories",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        anchor_service, "extract_and_store_anchors",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        anchor_service, "increment_hit_counts_bg",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        chat_service, "maybe_generate_summary",
        AsyncMock(return_value=None),
    )

    # 5. Subscription benefit lookup — avoid touching subscription tables.
    monkeypatch.setattr(
        chat_service, "_check_subscription_benefits",
        AsyncMock(return_value={
            "tier": "free",
            "hd_images": False,
            "exclusive_scenes": False,
            "priority_dm": False,
            "unlimited_replay": False,
        }),
    )

    return fake_chat


@pytest.mark.asyncio
async def test_handle_user_message_builds_context(
    db: AsyncSession, sample_persona, _patched_orchestration,
):
    """handle_user_message should pass persona prompt, prior history, and
    intimacy through to chat_with_ai when assembling the context window."""
    user = await _make_user(db, email="orchestration_ctx@example.com")
    fake_chat = _patched_orchestration

    # Seed a couple of prior messages so chat_history is non-empty.
    db.add_all([
        ChatMessage(
            user_id=user.id, ai_id=sample_persona.id,
            role="user", content="earlier user turn",
            message_type="chat", delivered=1,
        ),
        ChatMessage(
            user_id=user.id, ai_id=sample_persona.id,
            role="assistant", content="earlier ai turn",
            message_type="chat", delivered=1,
        ),
    ])
    await db.commit()

    result = await chat_service.handle_user_message(
        db=db,
        user=user,
        ai_id=sample_persona.id,
        message="What should we talk about today?",
    )

    # AI was called with history including only the prior turns.
    fake_chat.assert_awaited_once()
    kwargs = fake_chat.await_args.kwargs
    assert kwargs["user_message"] == "What should we talk about today?"
    assert kwargs["persona_prompt"].startswith(sample_persona.personality_prompt[:20])
    history = kwargs["chat_history"]
    assert [h["content"] for h in history] == ["earlier user turn", "earlier ai turn"]
    # Intimacy starts at 0 for a brand-new interaction.
    assert kwargs["intimacy"] == 0.0
    assert result.reply == "Mocked AI reply."


@pytest.mark.asyncio
async def test_handle_user_message_persists_both(
    db: AsyncSession, sample_persona, _patched_orchestration,
):
    """Both the user message and the AI reply must be persisted to the DB."""
    user = await _make_user(db, email="orchestration_persist@example.com")

    result = await chat_service.handle_user_message(
        db=db,
        user=user,
        ai_id=sample_persona.id,
        message="Hello there",
    )

    # Yield once so any incidentally scheduled mock tasks settle.
    await asyncio.sleep(0)

    rows = await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.user_id == user.id,
            ChatMessage.ai_id == sample_persona.id,
        )
        .order_by(ChatMessage.id.asc())
    )
    messages = list(rows.scalars().all())
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Hello there"
    assert messages[0].id == result.user_message_id
    assert messages[1].role == "assistant"
    assert messages[1].content == "Mocked AI reply."
    assert messages[1].id == result.ai_message_id
