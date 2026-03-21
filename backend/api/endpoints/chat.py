"""Chat API: REST and WebSocket endpoints for messaging AI personas.

POST /api/chat/send — send a message, receive AI reply
GET  /api/chat/history/{ai_id} — paginated chat history
GET  /api/chat/conversations — list all conversations
GET  /api/chat/unread-count — total unread count
POST /api/chat/mark-read/{ai_id} — mark conversation as read
DELETE /api/chat/messages/{id} — delete a message
WS   /api/chat/ws/{ai_id}?token= — real-time bidirectional chat
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete, and_, case

from core.database import get_db, async_session
from core.security import get_current_user, authenticate_ws_token
from core.ws_manager import get_ws_manager
from core.utils import to_utc_iso
from models.user import User
from models.chat_message import ChatMessage
from models.ai_persona import AIPersona
from models.interaction import Interaction
from services import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


# ── Request / Response schemas ──────────────────────────────────

class ChatRequest(BaseModel):
    ai_id: int
    message: str
    post_context: str | None = None


class ChatResponse(BaseModel):
    reply: str
    intimacy: float
    message_id: int | None = None
    nickname_proposal: dict | None = None
    emotion_hint: dict | None = None


class HistoryMessage(BaseModel):
    id: int
    role: str
    content: str
    message_type: str
    event: str | None = None
    created_at: str


class HistoryResponse(BaseModel):
    messages: list[HistoryMessage]
    has_more: bool


class ConversationOut(BaseModel):
    ai_id: int
    ai_name: str
    ai_avatar: str
    last_message: str
    last_message_at: str
    unread_count: int
    intimacy_score: float


# ── POST /send ──────────────────────────────────────────────────

@router.post("/send", response_model=ChatResponse)
async def send_message(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a chat message to an AI persona, returns AI reply."""
    try:
        result = await chat_service.handle_user_message(
            db=db,
            user=current_user,
            ai_id=body.ai_id,
            message=body.message,
            post_context=body.post_context,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ChatResponse(
        reply=result.reply,
        intimacy=result.intimacy,
        message_id=result.ai_message_id,
        nickname_proposal=result.nickname_proposal,
        emotion_hint=result.emotion_hint,
    )


# ── GET /conversations ──────────────────────────────────────────

@router.get("/conversations", response_model=list[ConversationOut])
async def get_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all AI conversations for the current user with last message and unread count."""
    # Get distinct AI IDs the user has chatted with
    ai_ids_result = await db.execute(
        select(ChatMessage.ai_id)
        .where(ChatMessage.user_id == current_user.id)
        .distinct()
    )
    ai_ids = [row[0] for row in ai_ids_result.all()]

    if not ai_ids:
        return []

    # Load personas
    personas_result = await db.execute(
        select(AIPersona).where(AIPersona.id.in_(ai_ids))
    )
    persona_map = {p.id: p for p in personas_result.scalars().all()}

    # Load interactions for intimacy
    interactions_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id.in_(ai_ids),
        )
    )
    intimacy_map = {i.ai_id: i.intimacy_score for i in interactions_result.scalars().all()}

    conversations = []
    for ai_id in ai_ids:
        persona = persona_map.get(ai_id)
        if not persona:
            continue

        # Get last message
        last_msg_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == current_user.id, ChatMessage.ai_id == ai_id)
            .order_by(ChatMessage.id.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        # Count unread (assistant messages that are undelivered proactive DMs)
        unread_result = await db.execute(
            select(func.count(ChatMessage.id))
            .where(
                ChatMessage.user_id == current_user.id,
                ChatMessage.ai_id == ai_id,
                ChatMessage.role == "assistant",
                ChatMessage.delivered == 0,
            )
        )
        unread_count = unread_result.scalar() or 0

        conversations.append(ConversationOut(
            ai_id=ai_id,
            ai_name=persona.name,
            ai_avatar=persona.avatar_url,
            last_message=last_msg.content[:100] if last_msg else "",
            last_message_at=to_utc_iso(last_msg.created_at) if last_msg and last_msg.created_at else "",
            unread_count=unread_count,
            intimacy_score=intimacy_map.get(ai_id, 0.0),
        ))

    # Sort by last message time descending
    conversations.sort(key=lambda c: c.last_message_at, reverse=True)
    return conversations


# ── GET /unread-count ───────────────────────────────────────────

@router.get("/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get total unread message count across all AI conversations."""
    result = await db.execute(
        select(func.count(ChatMessage.id))
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.role == "assistant",
            ChatMessage.delivered == 0,
        )
    )
    return {"unread_count": result.scalar() or 0}


# ── POST /mark-read/{ai_id} ────────────────────────────────────

@router.post("/mark-read/{ai_id}")
async def mark_conversation_read(
    ai_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all messages in a conversation as delivered/read."""
    await db.execute(
        update(ChatMessage)
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.ai_id == ai_id,
            ChatMessage.delivered == 0,
        )
        .values(delivered=1)
    )
    await db.commit()
    return {"message": "Conversation marked as read"}


# ── DELETE /messages/{id} ───────────────────────────────────────

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a single message (user can only delete their own)."""
    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.id == message_id,
            ChatMessage.user_id == current_user.id,
        )
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")

    await db.delete(msg)
    await db.commit()
    return {"message": "Message deleted"}


# ── GET /history/{ai_id} ───────────────────────────────────────

@router.get("/history/{ai_id}", response_model=HistoryResponse)
async def get_chat_history(
    ai_id: int,
    limit: int = Query(default=30, ge=1, le=100),
    before_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve paginated chat history for a user-AI pair."""
    messages = await chat_service.get_history(
        db=db,
        user_id=current_user.id,
        ai_id=ai_id,
        limit=limit + 1,
        before_id=before_id,
    )

    has_more = len(messages) > limit
    if has_more:
        messages = messages[1:]

    undelivered_ids = [m.id for m in messages if m.delivered == 0]
    if undelivered_ids:
        await chat_service.mark_delivered(db, undelivered_ids)
        await db.commit()

    return HistoryResponse(
        messages=[
            HistoryMessage(
                id=m.id,
                role=m.role,
                content=m.content,
                message_type=m.message_type,
                event=m.event,
                created_at=to_utc_iso(m.created_at) if m.created_at else "",
            )
            for m in messages
        ],
        has_more=has_more,
    )


# ── WebSocket ───────────────────────────────────────────────────

@router.websocket("/ws/{ai_id}")
async def websocket_chat(
    websocket: WebSocket,
    ai_id: int,
    token: str = Query(...),
):
    """Real-time chat via WebSocket."""
    manager = get_ws_manager()
    user: User | None = None

    async with async_session() as db:
        user = await authenticate_ws_token(token, db)

    if not user:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    await manager.connect(user.id, ai_id, websocket)

    try:
        while True:
            try:
                raw = await websocket.receive_text()
                data = json.loads(raw)
            except json.JSONDecodeError:
                await _send_error(websocket, "invalid_json", "Message must be valid JSON")
                continue

            msg_type = data.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "message":
                await _handle_chat_message(websocket, user, ai_id, data.get("data", {}))
            else:
                await _send_error(websocket, "unknown_type", f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("WebSocket error for user_id=%d ai_id=%d", user.id, ai_id)
    finally:
        manager.disconnect(user.id, ai_id)


async def _handle_chat_message(
    websocket: WebSocket,
    user: User,
    ai_id: int,
    data: dict,
) -> None:
    """Process an incoming chat message via WebSocket."""
    text = data.get("text", "").strip()
    if not text:
        await _send_error(websocket, "empty_message", "Message text cannot be empty")
        return

    post_context = data.get("post_context")

    async with async_session() as db:
        try:
            result = await chat_service.handle_user_message(
                db=db,
                user=user,
                ai_id=ai_id,
                message=text,
                post_context=post_context,
            )
        except ValueError as e:
            await _send_error(websocket, "not_found", str(e))
            return
        except Exception:
            logger.exception("Chat handler error for user_id=%d ai_id=%d", user.id, ai_id)
            await _send_error(websocket, "internal_error", "Failed to process message")
            return

    await websocket.send_json({
        "type": "message_saved",
        "data": {
            "message_id": result.user_message_id,
            "timestamp": None,
        },
    })

    reply_data = {
        "message_id": result.ai_message_id,
        "text": result.reply,
        "intimacy": result.intimacy,
    }
    if result.emotion_hint:
        reply_data["emotion_hint"] = result.emotion_hint
    if result.nickname_proposal:
        reply_data["nickname_proposal"] = result.nickname_proposal

    await websocket.send_json({
        "type": "ai_reply",
        "data": reply_data,
    })


async def _send_error(websocket: WebSocket, code: str, detail: str) -> None:
    """Send an error message to the client."""
    await websocket.send_json({
        "type": "error",
        "data": {"code": code, "detail": detail},
    })
