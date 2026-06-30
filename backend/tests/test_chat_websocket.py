"""
Chat WebSocket Endpoint Tests

Covers ``backend/api/endpoints/chat.py`` WebSocket route at
``/api/chat/ws/{ai_id}?token=...``. The endpoint supports a JSON message
protocol with the following types:

Client -> Server:
- ``{"type": "ping"}`` - heartbeat
- ``{"type": "message", "data": {"text": "...", "post_context": "..."}}``

Server -> Client:
- ``{"type": "pong"}``
- ``{"type": "message_saved", "data": {"message_id": ..., "timestamp": ...}}``
- ``{"type": "ai_reply", "data": {"message_id": ..., "text": ..., "intimacy": ...}}``
- ``{"type": "error", "data": {"code": ..., "detail": ...}}``

These tests use ``fastapi.testclient.TestClient`` (synchronous) which is the
recommended approach for FastAPI WebSocket testing. The chat orchestration
layer (``chat_service.handle_user_message``) and DB session factory used
inside the WS handler are patched so the tests do not hit the real Aliyun
LLM, vector store, or production database.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_user():
    """Return a lightweight stand-in for the authenticated User ORM row."""
    user = MagicMock()
    user.id = 1
    user.email = "ws_user@example.com"
    user.nickname = "WSUser"
    return user


@pytest.fixture
def patch_ws(monkeypatch, fake_user):
    """Patch WebSocket endpoint dependencies.

    - ``authenticate_ws_token`` accepts any non-empty, non-"invalid" token.
    - ``async_session`` returns a no-op async context manager so we never
      touch the real DB during WS auth or message handling.
    - ``chat_service.handle_user_message`` returns a deterministic
      ``ChatResult`` (raises ``ValueError`` for the magic ai_id 999_999 to
      simulate a missing persona).
    """
    from api.endpoints import chat as chat_module
    from services import chat_service
    from services.chat_service import ChatResult

    async def fake_authenticate(token, db):
        if not token or token == "invalid_token":
            return None
        return fake_user

    async def fake_handle(db, user, ai_id, message, post_context=None, **kwargs):
        if ai_id == 999_999:
            raise ValueError("AI persona not found")
        return ChatResult(
            reply=f"echo:{message}",
            user_message_id=100,
            ai_message_id=101,
            intimacy=7.5,
        )

    auth_mock = AsyncMock(side_effect=fake_authenticate)
    handle_mock = AsyncMock(side_effect=fake_handle)

    class _FakeAsyncSessionCM:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _fake_session_factory():
        return _FakeAsyncSessionCM()

    monkeypatch.setattr(chat_module, "authenticate_ws_token", auth_mock)
    monkeypatch.setattr(chat_module, "async_session", _fake_session_factory)
    monkeypatch.setattr(chat_service, "handle_user_message", handle_mock)

    return {
        "auth_mock": auth_mock,
        "handle_mock": handle_mock,
        "user": fake_user,
        "ChatResult": ChatResult,
        "chat_module": chat_module,
        "chat_service": chat_service,
    }


@pytest.fixture(autouse=True)
def reset_ws_manager():
    """Reset the global ``ConnectionManager`` between tests so leaked
    connections from a previous test do not pollute is_connected checks.
    """
    import core.ws_manager as ws_manager_module

    yield

    if ws_manager_module._manager is not None:
        ws_manager_module._manager._connections.clear()


@pytest.fixture
def ws_client(patch_ws):
    """Provide a ``TestClient`` with all WS dependencies patched."""
    with TestClient(app) as c:
        yield c


def _open_ws(client: TestClient, ai_id: int, token: str):
    """Return a WebSocket session context manager for the given AI / token."""
    return client.websocket_connect(f"/api/chat/ws/{ai_id}?token={token}")


# ──────────────────────────────────────────────────────────────────────
# Connection / authentication
# ──────────────────────────────────────────────────────────────────────


class TestWebSocketAuth:
    """Connection establishment and token validation."""

    def test_ws_connect_authenticated(self, ws_client: TestClient, patch_ws):
        """Valid token -> connection accepted, ping/pong roundtrip works."""
        with _open_ws(ws_client, ai_id=1, token="valid_token_123") as ws:
            ws.send_json({"type": "ping"})
            reply = ws.receive_json()
            assert reply == {"type": "pong"}

        # Authenticator was invoked exactly once for this connection
        patch_ws["auth_mock"].assert_awaited()

    def test_ws_connect_invalid_token(self, ws_client: TestClient):
        """Bad token -> server closes with code 4001 before any traffic."""
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with _open_ws(ws_client, ai_id=1, token="invalid_token") as ws:
                # Server should close immediately; reading triggers the disconnect
                ws.receive_json()
        assert exc_info.value.code == 4001

    def test_ws_connect_missing_token_rejected(self, ws_client: TestClient):
        """Empty token -> rejected by FastAPI (token is required) or 4001."""
        # FastAPI marks ``token: str = Query(...)`` as required, so omitting
        # it should produce a 403 close before our handler even runs. We
        # accept either behavior (close with 1008/4001 or HTTP 403).
        try:
            with ws_client.websocket_connect("/api/chat/ws/1") as ws:
                ws.receive_json()
        except WebSocketDisconnect as exc:
            assert exc.code in (1008, 4001, 4003)
        except Exception as exc:
            # Starlette raises a plain Exception (or HTTPException) for
            # missing required query params during WS handshake.
            assert "403" in str(exc) or "token" in str(exc).lower()


# ──────────────────────────────────────────────────────────────────────
# Message protocol
# ──────────────────────────────────────────────────────────────────────


class TestWebSocketMessaging:
    """Bidirectional message protocol behavior."""

    def test_ws_send_message_receive_reply(
        self, ws_client: TestClient, patch_ws
    ):
        """Full chat roundtrip emits ``message_saved`` then ``ai_reply``."""
        with _open_ws(ws_client, ai_id=42, token="good_token") as ws:
            ws.send_json(
                {
                    "type": "message",
                    "data": {"text": "hello there", "post_context": None},
                }
            )

            saved = ws.receive_json()
            ai_reply = ws.receive_json()

        assert saved["type"] == "message_saved"
        assert saved["data"]["message_id"] == 100

        assert ai_reply["type"] == "ai_reply"
        assert ai_reply["data"]["text"] == "echo:hello there"
        assert ai_reply["data"]["message_id"] == 101
        assert ai_reply["data"]["intimacy"] == 7.5

        # Verify chat_service.handle_user_message was invoked correctly
        patch_ws["handle_mock"].assert_awaited_once()
        call_kwargs = patch_ws["handle_mock"].await_args.kwargs
        assert call_kwargs["ai_id"] == 42
        assert call_kwargs["message"] == "hello there"

    def test_ws_invalid_message_format(self, ws_client: TestClient):
        """Malformed JSON -> ``error`` envelope with code ``invalid_json``."""
        with _open_ws(ws_client, ai_id=1, token="good_token") as ws:
            ws.send_text("not-json{")
            reply = ws.receive_json()

        assert reply["type"] == "error"
        assert reply["data"]["code"] == "invalid_json"

    def test_ws_unknown_message_type(self, ws_client: TestClient):
        """Unknown ``type`` field -> ``error`` envelope (unknown_type)."""
        with _open_ws(ws_client, ai_id=1, token="good_token") as ws:
            ws.send_json({"type": "definitely-not-a-real-type"})
            reply = ws.receive_json()

        assert reply["type"] == "error"
        assert reply["data"]["code"] == "unknown_type"

    def test_ws_empty_message_text(self, ws_client: TestClient, patch_ws):
        """Empty ``text`` -> ``error`` envelope; chat_service NOT called."""
        with _open_ws(ws_client, ai_id=1, token="good_token") as ws:
            ws.send_json({"type": "message", "data": {"text": "   "}})
            reply = ws.receive_json()

        assert reply["type"] == "error"
        assert reply["data"]["code"] == "empty_message"
        patch_ws["handle_mock"].assert_not_awaited()

    def test_ws_persona_not_found(self, ws_client: TestClient, patch_ws):
        """Unknown ai_id (handler raises ValueError) -> ``not_found`` error."""
        with _open_ws(ws_client, ai_id=999_999, token="good_token") as ws:
            ws.send_json({"type": "message", "data": {"text": "hi"}})
            reply = ws.receive_json()

        assert reply["type"] == "error"
        assert reply["data"]["code"] == "not_found"


# ──────────────────────────────────────────────────────────────────────
# Heartbeat
# ──────────────────────────────────────────────────────────────────────


class TestWebSocketHeartbeat:
    """Ping/pong keepalive mechanism."""

    def test_ws_heartbeat_keepalive(self, ws_client: TestClient):
        """Multiple pings receive matching pong responses on same socket."""
        with _open_ws(ws_client, ai_id=1, token="good_token") as ws:
            for _ in range(3):
                ws.send_json({"type": "ping"})
                reply = ws.receive_json()
                assert reply == {"type": "pong"}


# ──────────────────────────────────────────────────────────────────────
# Lifecycle: disconnect, reconnect, concurrency
# ──────────────────────────────────────────────────────────────────────


class TestWebSocketLifecycle:
    """Connection cleanup, reconnection, and concurrent sessions."""

    def test_ws_disconnect_cleanup(self, ws_client: TestClient):
        """After client closes, ``ConnectionManager`` no longer tracks it."""
        from core.ws_manager import get_ws_manager

        manager = get_ws_manager()

        with _open_ws(ws_client, ai_id=7, token="good_token") as ws:
            ws.send_json({"type": "ping"})
            ws.receive_json()
            # While connected, the manager should know about us
            assert manager.is_connected(user_id=1, ai_id=7)

        # Give the server's ``finally`` block a moment to run
        for _ in range(20):
            if not manager.is_connected(user_id=1, ai_id=7):
                break
            time.sleep(0.05)

        assert not manager.is_connected(user_id=1, ai_id=7)

    def test_ws_reconnect_after_disconnect(self, ws_client: TestClient):
        """A fresh connection works after the previous one is closed."""
        # First session
        with _open_ws(ws_client, ai_id=3, token="good_token") as ws1:
            ws1.send_json({"type": "ping"})
            assert ws1.receive_json() == {"type": "pong"}

        # Allow cleanup
        time.sleep(0.1)

        # Second session on same user/AI pair
        with _open_ws(ws_client, ai_id=3, token="good_token") as ws2:
            ws2.send_json({"type": "ping"})
            assert ws2.receive_json() == {"type": "pong"}

    def test_ws_concurrent_connections(self, ws_client: TestClient):
        """Same user can hold simultaneous sessions for different AI ids."""
        from core.ws_manager import get_ws_manager

        manager = get_ws_manager()

        with _open_ws(ws_client, ai_id=11, token="good_token") as ws_a, \
             _open_ws(ws_client, ai_id=22, token="good_token") as ws_b:
            ws_a.send_json({"type": "ping"})
            ws_b.send_json({"type": "ping"})

            assert ws_a.receive_json() == {"type": "pong"}
            assert ws_b.receive_json() == {"type": "pong"}

            assert manager.is_connected(user_id=1, ai_id=11)
            assert manager.is_connected(user_id=1, ai_id=22)


# ──────────────────────────────────────────────────────────────────────
# Persistence delegation
# ──────────────────────────────────────────────────────────────────────


class TestWebSocketPersistence:
    """Verify the WS endpoint delegates persistence to ``chat_service``.

    The actual DB writes are owned by ``chat_service.handle_user_message``
    (already covered by ``test_chat.py`` and service-layer tests). Here we
    only assert that the WS handler routes user input through that
    persistence-bearing helper with the correct arguments.
    """

    def test_ws_message_persisted(self, ws_client: TestClient, patch_ws):
        """Sending a chat message via WS triggers chat_service persistence."""
        with _open_ws(ws_client, ai_id=5, token="good_token") as ws:
            ws.send_json(
                {
                    "type": "message",
                    "data": {"text": "store me please", "post_context": "ctx"},
                }
            )
            # Drain ``message_saved`` + ``ai_reply``
            ws.receive_json()
            ws.receive_json()

        # The persistence-bearing service was called exactly once with the
        # user's text and post_context.
        patch_ws["handle_mock"].assert_awaited_once()
        call_kwargs = patch_ws["handle_mock"].await_args.kwargs
        assert call_kwargs["ai_id"] == 5
        assert call_kwargs["message"] == "store me please"
        assert call_kwargs["post_context"] == "ctx"
        assert call_kwargs["user"].id == patch_ws["user"].id


# ──────────────────────────────────────────────────────────────────────
# Features not implemented by the current endpoint
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.skip(
    reason=(
        "Typing indicator messages are not part of the current WS protocol. "
        "Endpoint supports only: ping, message (client) -> pong, "
        "message_saved, ai_reply, error (server). Skipped per spec guidance "
        "to skip gracefully when a feature is absent."
    )
)
def test_ws_typing_indicator():
    """Placeholder for future typing-indicator support."""
    pass
