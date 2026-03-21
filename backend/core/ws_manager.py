"""WebSocket connection manager for real-time chat.

Singleton that tracks active WebSocket connections per user-AI pair.
Enables server-initiated pushes (proactive DMs) and connection management.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections for user-AI chat pairs.

    Structure: {user_id: {ai_id: WebSocket}}

    Each user can have multiple connections (one per AI persona they're
    chatting with), but only one connection per AI persona at a time.
    """

    def __init__(self) -> None:
        # user_id -> ai_id -> WebSocket
        self._connections: dict[int, dict[int, WebSocket]] = {}

    async def connect(self, user_id: int, ai_id: int, websocket: WebSocket) -> None:
        """Accept and register a new WebSocket connection.

        If there's an existing connection for this user-AI pair, it gets replaced.
        """
        await websocket.accept()

        if user_id not in self._connections:
            self._connections[user_id] = {}

        # Close existing connection if any (new tab/reconnect scenario)
        existing = self._connections[user_id].get(ai_id)
        if existing:
            try:
                await existing.close(code=4000, reason="Replaced by new connection")
            except Exception:
                pass  # Already closed

        self._connections[user_id][ai_id] = websocket
        logger.info("WS connected: user_id=%d ai_id=%d", user_id, ai_id)

    def disconnect(self, user_id: int, ai_id: int) -> None:
        """Remove a connection from tracking (call on disconnect/error)."""
        if user_id in self._connections:
            self._connections[user_id].pop(ai_id, None)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.info("WS disconnected: user_id=%d ai_id=%d", user_id, ai_id)

    def is_connected(self, user_id: int, ai_id: int) -> bool:
        """Check if a user-AI pair has an active connection."""
        return (
            user_id in self._connections
            and ai_id in self._connections[user_id]
        )

    def get_websocket(self, user_id: int, ai_id: int) -> WebSocket | None:
        """Get the WebSocket for a user-AI pair, or None if not connected."""
        return self._connections.get(user_id, {}).get(ai_id)

    async def send_json(
        self,
        user_id: int,
        ai_id: int,
        message: dict[str, Any],
    ) -> bool:
        """Send a JSON message to a specific user-AI connection.

        Returns True if sent successfully, False if not connected or error.
        """
        ws = self.get_websocket(user_id, ai_id)
        if ws is None:
            return False

        try:
            await ws.send_json(message)
            return True
        except Exception:
            logger.warning(
                "Failed to send WS message to user_id=%d ai_id=%d",
                user_id, ai_id, exc_info=True,
            )
            self.disconnect(user_id, ai_id)
            return False

    async def broadcast_to_user(
        self,
        user_id: int,
        message: dict[str, Any],
    ) -> int:
        """Send a message to all AI connections for a user.

        Returns count of successful sends.
        """
        if user_id not in self._connections:
            return 0

        success_count = 0
        # Copy keys to avoid modification during iteration
        ai_ids = list(self._connections.get(user_id, {}).keys())
        for ai_id in ai_ids:
            if await self.send_json(user_id, ai_id, message):
                success_count += 1
        return success_count

    def get_stats(self) -> dict[str, int]:
        """Return connection statistics for monitoring."""
        total_connections = sum(
            len(ai_conns) for ai_conns in self._connections.values()
        )
        return {
            "active_users": len(self._connections),
            "total_connections": total_connections,
        }


# ── Singleton instance ──────────────────────────────────────────

_manager: ConnectionManager | None = None


def get_ws_manager() -> ConnectionManager:
    """Get the global ConnectionManager singleton."""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
