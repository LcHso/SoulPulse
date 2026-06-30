"""
Chat REST Endpoint Tests

Covers ``backend/api/endpoints/chat.py``:
- POST   /api/chat/send
- GET    /api/chat/history/{ai_id}
- GET    /api/chat/conversations
- GET    /api/chat/unread-count
- POST   /api/chat/mark-read/{ai_id}
- DELETE /api/chat/messages/{message_id}

The ``chat_service`` orchestration layer is mocked so tests do not hit
the real Aliyun LLM, vector store, or background scheduler. ``ChatMessage``
rows are inserted directly into the test DB to exercise the read paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.chat_message import ChatMessage
from models.user import User


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


_INVALID_AI_ID = 999_999


async def _get_user_by_email(db: AsyncSession, email: str) -> User:
    """Fetch the User row created by ``auth_client``."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    assert user is not None, f"Test user {email} not found"
    return user


async def _register_and_login(client: AsyncClient, email: str, nickname: str) -> str:
    """Register a fresh user, log in, attach the bearer token to ``client``
    and return that token. Used to obtain an isolated user for tests whose
    assertions are sensitive to cross-test data accumulation in the
    session-scoped in-memory database.
    """
    await client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "TestPass123!",
            "nickname": nickname,
        },
    )
    login = await client.post(
        "/api/auth/login",
        data={"username": email, "password": "TestPass123!"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return token


async def _seed_messages(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
    *,
    user_msgs: int = 0,
    ai_msgs: int = 0,
    delivered: int = 1,
) -> list[ChatMessage]:
    """Insert ``user_msgs`` user messages and ``ai_msgs`` assistant messages
    for the given conversation. Returns the inserted rows in insertion order.
    """
    rows: list[ChatMessage] = []
    for i in range(user_msgs):
        rows.append(
            ChatMessage(
                user_id=user_id,
                ai_id=ai_id,
                role="user",
                content=f"user message {i}",
                message_type="chat",
                delivered=1,
            )
        )
    for i in range(ai_msgs):
        rows.append(
            ChatMessage(
                user_id=user_id,
                ai_id=ai_id,
                role="assistant",
                content=f"ai message {i}",
                message_type="chat",
                delivered=delivered,
            )
        )
    db.add_all(rows)
    await db.commit()
    for r in rows:
        await db.refresh(r)
    return rows


# ──────────────────────────────────────────────────────────────────────
# Fixtures local to chat tests
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_chat_pipeline(monkeypatch):
    """Replace the ``chat_service`` orchestration helpers with safe stubs.

    - ``handle_user_message`` returns a fixed ``ChatResult`` (raises
      ``ValueError`` for the sentinel ``_INVALID_AI_ID`` so the endpoint can
      surface a 404).
    - ``check_is_first_chat`` reports False so the history endpoint does not
      auto-generate a welcome message during list-style tests.
    - ``generate_welcome_message`` / ``persist_message`` are stubbed for
      completeness in case a test toggles ``check_is_first_chat``.
    """
    from services import chat_service
    from services.chat_service import ChatResult

    async def fake_handle(db, user, ai_id, message, post_context=None, **kwargs):
        if ai_id == _INVALID_AI_ID:
            raise ValueError("AI persona not found")
        return ChatResult(
            reply="This is a mocked AI reply.",
            user_message_id=1,
            ai_message_id=2,
            intimacy=5.0,
        )

    async def fake_check_is_first_chat(*args, **kwargs):
        return False

    async def fake_welcome(*args, **kwargs):
        return "Welcome!"

    monkeypatch.setattr(
        chat_service,
        "handle_user_message",
        AsyncMock(side_effect=fake_handle),
    )
    monkeypatch.setattr(
        chat_service,
        "check_is_first_chat",
        AsyncMock(side_effect=fake_check_is_first_chat),
    )
    monkeypatch.setattr(
        chat_service,
        "generate_welcome_message",
        AsyncMock(side_effect=fake_welcome),
    )
    return chat_service


# ──────────────────────────────────────────────────────────────────────
# POST /api/chat/send
# ──────────────────────────────────────────────────────────────────────


class TestSendMessage:
    """Tests for ``POST /api/chat/send``."""

    @pytest.mark.asyncio
    async def test_send_message_success(
        self,
        auth_client: AsyncClient,
        sample_persona,
        mock_chat_pipeline,
    ):
        """Valid send request returns AI reply payload."""
        resp = await auth_client.post(
            "/api/chat/send",
            json={"ai_id": sample_persona.id, "message": "你好"},
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["reply"] == "This is a mocked AI reply."
        assert data["intimacy"] == 5.0
        assert data["message_id"] == 2

    @pytest.mark.asyncio
    async def test_send_message_unauthenticated(
        self,
        client: AsyncClient,
        sample_persona,
    ):
        """Missing auth token returns 401."""
        resp = await client.post(
            "/api/chat/send",
            json={"ai_id": sample_persona.id, "message": "hi"},
        )

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_send_message_invalid_ai_id(
        self,
        auth_client: AsyncClient,
        mock_chat_pipeline,
    ):
        """Non-existent AI persona id raises ValueError → 404."""
        resp = await auth_client.post(
            "/api/chat/send",
            json={"ai_id": _INVALID_AI_ID, "message": "hi"},
        )

        assert resp.status_code == 404
        assert "AI persona not found" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_send_message_empty_content(
        self,
        auth_client: AsyncClient,
        sample_persona,
        mock_chat_pipeline,
    ):
        """Missing required ``message`` field is rejected by FastAPI (422)."""
        resp = await auth_client.post(
            "/api/chat/send",
            json={"ai_id": sample_persona.id},  # no "message" key
        )

        assert resp.status_code == 422


# ──────────────────────────────────────────────────────────────────────
# GET /api/chat/history/{ai_id}
# ──────────────────────────────────────────────────────────────────────


class TestChatHistory:
    """Tests for ``GET /api/chat/history/{ai_id}``."""

    @pytest.mark.asyncio
    async def test_get_history_success(
        self,
        auth_client: AsyncClient,
        db: AsyncSession,
        sample_persona,
        mock_chat_pipeline,
    ):
        """History endpoint returns persisted messages in chronological order."""
        user = await _get_user_by_email(db, "testuser@example.com")
        await _seed_messages(
            db, user.id, sample_persona.id, user_msgs=3, ai_msgs=2
        )

        resp = await auth_client.get(f"/api/chat/history/{sample_persona.id}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["has_more"] is False
        assert len(body["messages"]) == 5
        # Service returns ascending order by id
        ids = [m["id"] for m in body["messages"]]
        assert ids == sorted(ids)
        roles = [m["role"] for m in body["messages"]]
        assert "user" in roles and "assistant" in roles

    @pytest.mark.asyncio
    async def test_get_history_empty(
        self,
        auth_client: AsyncClient,
        sample_persona,
        mock_chat_pipeline,
    ):
        """Brand-new conversation returns an empty list (welcome stub off)."""
        resp = await auth_client.get(f"/api/chat/history/{sample_persona.id}")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["messages"] == []
        assert body["has_more"] is False

    @pytest.mark.asyncio
    async def test_get_history_cursor_pagination(
        self,
        auth_client: AsyncClient,
        db: AsyncSession,
        sample_persona,
        mock_chat_pipeline,
    ):
        """``limit`` + ``before_id`` performs cursor pagination."""
        user = await _get_user_by_email(db, "testuser@example.com")
        rows = await _seed_messages(
            db, user.id, sample_persona.id, user_msgs=6
        )
        all_ids = sorted(r.id for r in rows)

        # First page (newest 2 messages)
        first = await auth_client.get(
            f"/api/chat/history/{sample_persona.id}?limit=2"
        )
        assert first.status_code == 200, first.text
        page1 = first.json()
        assert len(page1["messages"]) == 2
        assert page1["has_more"] is True
        page1_ids = [m["id"] for m in page1["messages"]]
        # Newest messages are the last two seeded
        assert page1_ids == all_ids[-2:]

        # Second page using before_id cursor
        before_id = page1_ids[0]
        second = await auth_client.get(
            f"/api/chat/history/{sample_persona.id}"
            f"?limit=2&before_id={before_id}"
        )
        assert second.status_code == 200, second.text
        page2 = second.json()
        assert len(page2["messages"]) == 2
        page2_ids = [m["id"] for m in page2["messages"]]
        # Page 2 ids must be strictly older than the first cursor
        assert all(mid < before_id for mid in page2_ids)
        assert page2["has_more"] is True


# ──────────────────────────────────────────────────────────────────────
# GET /api/chat/conversations
# ──────────────────────────────────────────────────────────────────────


class TestConversations:
    """Tests for ``GET /api/chat/conversations``."""

    @pytest.mark.asyncio
    async def test_get_conversations_list(
        self,
        client: AsyncClient,
        db: AsyncSession,
        sample_persona,
    ):
        """Returns an entry for every AI the user has chatted with."""
        await _register_and_login(
            client, "convo_list@test.com", "ConvoListUser"
        )
        user = await _get_user_by_email(db, "convo_list@test.com")
        await _seed_messages(
            db, user.id, sample_persona.id, user_msgs=1, ai_msgs=1
        )

        resp = await client.get("/api/chat/conversations")

        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert isinstance(items, list)
        assert len(items) == 1
        item = items[0]
        assert item["ai_id"] == sample_persona.id
        assert item["ai_name"] == sample_persona.name
        assert item["last_message"]  # non-empty
        assert "unread_count" in item
        assert "intimacy_score" in item

    @pytest.mark.asyncio
    async def test_get_conversations_empty(self, client: AsyncClient):
        """A user with no chat history gets an empty list."""
        await _register_and_login(
            client, "convo_empty@test.com", "ConvoEmptyUser"
        )

        resp = await client.get("/api/chat/conversations")

        assert resp.status_code == 200
        assert resp.json() == []


# ──────────────────────────────────────────────────────────────────────
# GET /api/chat/unread-count
# ──────────────────────────────────────────────────────────────────────


class TestUnreadCount:
    """Tests for ``GET /api/chat/unread-count`` and ``POST /mark-read``."""

    @pytest.mark.asyncio
    async def test_get_unread_count(
        self,
        client: AsyncClient,
        db: AsyncSession,
        sample_persona,
    ):
        """Counts only assistant messages with ``delivered=0``."""
        await _register_and_login(
            client, "unread_count@test.com", "UnreadCountUser"
        )
        user = await _get_user_by_email(db, "unread_count@test.com")
        # 2 undelivered AI messages, 1 delivered AI message, plus user msgs
        await _seed_messages(
            db, user.id, sample_persona.id, ai_msgs=2, delivered=0
        )
        await _seed_messages(
            db, user.id, sample_persona.id, ai_msgs=1, delivered=1
        )
        await _seed_messages(
            db, user.id, sample_persona.id, user_msgs=2
        )

        resp = await client.get("/api/chat/unread-count")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"unread_count": 2}

    @pytest.mark.asyncio
    async def test_mark_as_read(
        self,
        client: AsyncClient,
        db: AsyncSession,
        sample_persona,
    ):
        """``mark-read`` flips all undelivered AI messages to delivered=1."""
        await _register_and_login(
            client, "mark_read@test.com", "MarkReadUser"
        )
        user = await _get_user_by_email(db, "mark_read@test.com")
        await _seed_messages(
            db, user.id, sample_persona.id, ai_msgs=3, delivered=0
        )

        # Sanity: count should be 3 before marking read
        before = await client.get("/api/chat/unread-count")
        assert before.json()["unread_count"] == 3

        resp = await client.post(
            f"/api/chat/mark-read/{sample_persona.id}"
        )
        assert resp.status_code == 200
        assert resp.json() == {"message": "Conversation marked as read"}

        after = await client.get("/api/chat/unread-count")
        assert after.json()["unread_count"] == 0


# ──────────────────────────────────────────────────────────────────────
# DELETE /api/chat/messages/{id}
# ──────────────────────────────────────────────────────────────────────


class TestDeleteMessage:
    """Tests for ``DELETE /api/chat/messages/{message_id}``."""

    @pytest.mark.asyncio
    async def test_delete_message_success(
        self,
        auth_client: AsyncClient,
        db: AsyncSession,
        sample_persona,
    ):
        """User can delete a message they own."""
        user = await _get_user_by_email(db, "testuser@example.com")
        rows = await _seed_messages(
            db, user.id, sample_persona.id, user_msgs=1
        )
        msg_id = rows[0].id

        resp = await auth_client.delete(f"/api/chat/messages/{msg_id}")

        assert resp.status_code == 200, resp.text
        assert resp.json() == {"message": "Message deleted"}

        # Verify removal in DB
        gone = await db.execute(
            select(ChatMessage).where(ChatMessage.id == msg_id)
        )
        assert gone.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_message_not_found(self, auth_client: AsyncClient):
        """Unknown message id returns 404."""
        resp = await auth_client.delete("/api/chat/messages/999999")

        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_delete_message_wrong_user(
        self,
        auth_client: AsyncClient,
        db: AsyncSession,
        sample_persona,
    ):
        """A user cannot delete a message owned by someone else.

        The endpoint scopes the lookup by ``user_id``, so a foreign message
        is reported as missing (404) and remains in the database.
        """
        from core.security import hash_password

        # Create a separate user and a message owned by that user
        other = User(
            email="other_chat_user@example.com",
            hashed_password=hash_password("OtherPass123!"),
            nickname="OtherUser",
        )
        db.add(other)
        await db.commit()
        await db.refresh(other)

        rows = await _seed_messages(
            db, other.id, sample_persona.id, user_msgs=1
        )
        foreign_msg_id = rows[0].id

        resp = await auth_client.delete(
            f"/api/chat/messages/{foreign_msg_id}"
        )

        # Endpoint returns 404 because the row is not visible under the
        # authenticated user's scope — the foreign message must NOT be deleted.
        assert resp.status_code == 404

        still_there = await db.execute(
            select(ChatMessage).where(ChatMessage.id == foreign_msg_id)
        )
        assert still_there.scalar_one_or_none() is not None
