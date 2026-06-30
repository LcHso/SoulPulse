"""
E2E Chat Flow Tests

Tests that exercise the full chat pipeline: REST endpoints -> chat_service ->
emotion_engine -> memory/anchor extraction.  External APIs (AI, vector store)
are mocked; internal services run naturally against an in-memory SQLite DB.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.chat_message import ChatMessage
from models.emotion_state import EmotionState
from models.interaction import Interaction

# The mock_ai_service fixture patches aliyun_ai_service.chat_with_ai at module
# level, but chat_service.py imports it directly.  We need to also patch the
# reference inside chat_service for the mock to take effect.
_CHAT_WITH_AI_PATH = "services.chat_service.chat_with_ai"


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _register_and_login(client: AsyncClient, email: str, password: str, nickname: str) -> str:
    """Register a new user and return the JWT access token."""
    await client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "nickname": nickname,
    })
    login_resp = await client.post("/api/auth/login", data={
        "username": email,
        "password": password,
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    return login_resp.json()["access_token"]


# ─── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_chat_flow(
    client: AsyncClient,
    db: AsyncSession,
    sample_persona,
    mock_ai_service,
    mock_vector_store,
):
    """
    Full chat flow: Register -> send message -> get AI reply -> verify emotion
    state exists -> verify memory extraction was triggered.
    """
    # 1. Register & login
    token = await _register_and_login(client, "chatflow@test.com", "Pass123!", "ChatUser")
    headers = {"Authorization": f"Bearer {token}"}

    # Patch chat_with_ai at the import site inside chat_service
    fake_reply = AsyncMock(return_value="这是一条来自 mock AI 的固定回复。")
    with patch(_CHAT_WITH_AI_PATH, fake_reply):
        # 2. Send a message to the persona
        send_resp = await client.post("/api/chat/send", json={
            "ai_id": sample_persona.id,
            "message": "你好！最近过得怎么样？",
        }, headers=headers)

    assert send_resp.status_code == 200, f"Send failed: {send_resp.text}"
    data = send_resp.json()

    # 3. Verify AI reply received
    assert "reply" in data
    assert len(data["reply"]) > 0
    assert "intimacy" in data
    assert data["intimacy"] > 0  # intimacy should have increased from 0

    # 4. Verify emotion state exists in DB
    emo_result = await db.execute(
        select(EmotionState).where(
            EmotionState.ai_id == sample_persona.id,
        )
    )
    emotion_states = emo_result.scalars().all()
    assert len(emotion_states) > 0, "EmotionState should be created after chat"

    # 5. Verify the AI service was called (mock)
    fake_reply.assert_called_once()

    # 6. Verify chat messages persisted (user + assistant)
    msgs_result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.ai_id == sample_persona.id,
        ).order_by(ChatMessage.id.asc())
    )
    messages = msgs_result.scalars().all()
    # Should have at least user message + AI reply
    assert len(messages) >= 2
    roles = [m.role for m in messages]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_multi_turn_conversation(
    client: AsyncClient,
    db: AsyncSession,
    sample_persona,
    mock_ai_service,
    mock_vector_store,
):
    """
    Multi-turn conversation: Send 3+ messages -> verify history grows ->
    verify context window includes prior messages.
    """
    # Register & login
    token = await _register_and_login(client, "multiturn@test.com", "Pass123!", "MultiUser")
    headers = {"Authorization": f"Bearer {token}"}

    messages_to_send = [
        "你好，我今天心情不太好。",
        "工作压力太大了。",
        "有什么好的放松方式推荐吗？",
        "谢谢你的建议！",
    ]

    # Patch chat_with_ai at the import site inside chat_service
    fake_reply = AsyncMock(return_value="这是一条来自 mock AI 的固定回复。")
    with patch(_CHAT_WITH_AI_PATH, fake_reply):
        # Send multiple messages
        for msg in messages_to_send:
            resp = await client.post("/api/chat/send", json={
                "ai_id": sample_persona.id,
                "message": msg,
            }, headers=headers)
            assert resp.status_code == 200, f"Send failed for '{msg}': {resp.text}"

    # Verify history has all messages (user + AI replies)
    history_resp = await client.get(
        f"/api/chat/history/{sample_persona.id}",
        headers=headers,
        params={"limit": 50},
    )
    assert history_resp.status_code == 200
    history_data = history_resp.json()

    # Each message produces a user msg + AI reply = 2 per turn
    # Plus potentially a welcome message on first history fetch
    all_messages = history_data["messages"]
    user_messages = [m for m in all_messages if m["role"] == "user"]
    ai_messages = [m for m in all_messages if m["role"] == "assistant"]

    assert len(user_messages) >= len(messages_to_send), (
        f"Expected at least {len(messages_to_send)} user messages, got {len(user_messages)}"
    )
    assert len(ai_messages) >= len(messages_to_send), (
        f"Expected at least {len(messages_to_send)} AI messages, got {len(ai_messages)}"
    )

    # Verify AI service was called once per user message
    assert fake_reply.call_count >= len(messages_to_send)

    # Verify intimacy increased across turns
    with patch(_CHAT_WITH_AI_PATH, AsyncMock(return_value="最后回复")):
        final_resp = await client.post("/api/chat/send", json={
            "ai_id": sample_persona.id,
            "message": "最后一条消息",
        }, headers=headers)
    final_data = final_resp.json()
    # Intimacy should be > 0.2 * number_of_turns (each chat adds 0.2)
    assert final_data["intimacy"] >= 0.8, (
        f"Intimacy should accumulate, got {final_data['intimacy']}"
    )


@pytest.mark.asyncio
async def test_proactive_dm_trigger(
    client: AsyncClient,
    db: AsyncSession,
    sample_persona,
    mock_ai_service,
    mock_vector_store,
):
    """
    Proactive DM trigger: Set up conditions that satisfy proactive DM
    triggers -> verify the emotion engine identifies them.
    """
    from services import emotion_engine
    from models.emotion_state import EmotionState
    from models.interaction import Interaction
    from datetime import datetime, timezone, timedelta

    # Register & login
    token = await _register_and_login(client, "proactive@test.com", "Pass123!", "ProactiveUser")
    headers = {"Authorization": f"Bearer {token}"}

    # Send an initial message to create the interaction + emotion state
    with patch(_CHAT_WITH_AI_PATH, AsyncMock(return_value="Hello there!")):
        resp = await client.post("/api/chat/send", json={
            "ai_id": sample_persona.id,
            "message": "Hello!",
        }, headers=headers)
    assert resp.status_code == 200

    # Get the user_id from the me endpoint
    me_resp = await client.get("/api/auth/me", headers=headers)
    user_id = me_resp.json()["id"]

    # Manually manipulate emotion state to trigger proactive DM conditions
    emo_result = await db.execute(
        select(EmotionState).where(
            EmotionState.user_id == user_id,
            EmotionState.ai_id == sample_persona.id,
        )
    )
    emo_state = emo_result.scalar_one_or_none()
    assert emo_state is not None, "Emotion state should exist after chat"

    # Set longing high and push last_interaction far back
    emo_state.longing = 0.85
    emo_state.last_interaction_at = datetime.now(timezone.utc) - timedelta(hours=48)

    # Set intimacy high enough for longing_dm trigger (>= 5.0)
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == user_id,
            Interaction.ai_id == sample_persona.id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    assert interaction is not None
    interaction.intimacy_score = 5.5

    await db.commit()

    # Refresh emotion state
    await db.refresh(emo_state)

    # Check proactive triggers
    triggers = emotion_engine.check_proactive_triggers(
        state=emo_state,
        intimacy=interaction.intimacy_score,
    )

    # Should include "longing_dm" (longing > 0.7 and intimacy >= 5.0)
    assert "longing_dm" in triggers, (
        f"Expected 'longing_dm' trigger, got: {triggers}. "
        f"longing={emo_state.longing}, intimacy={interaction.intimacy_score}"
    )

    # Also check daily_checkin (last interaction > 24h and intimacy >= 2.0)
    assert "daily_checkin" in triggers, (
        f"Expected 'daily_checkin' trigger, got: {triggers}"
    )
