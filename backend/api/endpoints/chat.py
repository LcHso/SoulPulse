"""
聊天端点模块：REST 和 WebSocket 端点

================================================================================
功能概述
================================================================================
本模块提供用户与 AI 人格聊天交互的 REST API 和 WebSocket 端点：
- 发送消息：发送消息给 AI 人格并获取回复
- 获取历史记录：获取与 AI 的聊天历史（分页）
- 获取对话列表：获取所有对话及最后消息
- 获取未读数：获取跨 AI 的总未读消息数
- 标记已读：标记对话为已读
- 删除消息：删除单条消息
- WebSocket 实时聊天：双向实时消息传输

================================================================================
设计理念
================================================================================
1. REST 和 WebSocket 统一处理：
   - 两种方式都委托给 chat_service.handle_user_message() 处理
   - 确保行为一致，避免逻辑分散

2. WebSocket 认证：
   - 使用 URL 查询参数传递 JWT 令牌
   - 连接时验证令牌有效性

3. 消息投递状态：
   - 主动私信（proactive_dm）初始 delivered=0
   - 用户查看后标记为已投递

================================================================================
API 端点列表
================================================================================
POST   /api/chat/send              - 发送消息并获取回复
GET    /api/chat/history/{ai_id}   - 获取聊天历史
GET    /api/chat/conversations     - 获取对话列表
GET    /api/chat/unread-count      - 获取未读消息数
POST   /api/chat/mark-read/{ai_id} - 标记对话为已读
DELETE /api/chat/messages/{id}     - 删除消息
WS     /api/chat/ws/{ai_id}?token= - WebSocket 实时聊天
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


# ── 请求/响应数据模型 ──────────────────────────────────

class ChatRequest(BaseModel):
    """
    聊天请求模型。

    Attributes:
        ai_id: AI 人格 ID
        message: 用户消息内容
        post_context: 帖子上下文（可选，用于帖子相关聊天）
    """
    ai_id: int
    message: str
    post_context: str | None = None


class ChatResponse(BaseModel):
    """
    聊天响应模型。

    Attributes:
        reply: AI 回复内容
        intimacy: 更新后的亲密度分数
        message_id: AI 消息 ID（可选）
        nickname_proposal: 昵称提案（可选）
        emotion_hint: 情绪提示（可选）
    """
    reply: str
    intimacy: float
    message_id: int | None = None
    nickname_proposal: dict | None = None
    emotion_hint: dict | None = None


class HistoryMessage(BaseModel):
    """
    历史消息模型。

    Attributes:
        id: 消息 ID
        role: 消息角色（"user" 或 "assistant"）
        content: 消息内容
        message_type: 消息类型（"chat" 或 "proactive_dm"）
        event: 事件类型（可选）
        created_at: 创建时间
    """
    id: int
    role: str
    content: str
    message_type: str
    event: str | None = None
    created_at: str


class HistoryResponse(BaseModel):
    """
    历史记录响应模型。

    Attributes:
        messages: 消息列表
        has_more: 是否有更多消息
    """
    messages: list[HistoryMessage]
    has_more: bool


class ConversationOut(BaseModel):
    """
    对话输出模型。

    Attributes:
        ai_id: AI 人格 ID
        ai_name: AI 人格名称
        ai_avatar: AI 人格头像 URL
        last_message: 最后一条消息内容
        last_message_at: 最后消息时间
        unread_count: 未读消息数
        intimacy_score: 亲密度分数
    """
    ai_id: int
    ai_name: str
    ai_avatar: str
    last_message: str
    last_message_at: str
    unread_count: int
    intimacy_score: float


# ── POST /send 发送消息 ──────────────────────────────────────────────────

@router.post("/send", response_model=ChatResponse)
async def send_message(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    发送聊天消息给 AI 人格，返回 AI 回复。

    这是主要的聊天入口点，处理消息持久化、AI 回复生成、
    亲密度更新、情绪状态更新等。

    Args:
        body: 聊天请求体
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        ChatResponse: 包含 AI 回复和相关信息

    Raises:
        HTTPException: AI 人格不存在时返回 404 错误
    """
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


# ── GET /conversations 获取对话列表 ──────────────────────────────────────────

@router.get("/conversations", response_model=list[ConversationOut])
async def get_conversations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取当前用户的所有 AI 对话列表。

    返回每个对话的最后消息、未读消息数和亲密度分数。
    结果按最后消息时间降序排列。

    Args:
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        list[ConversationOut]: 对话列表
    """
    # 获取用户聊过天的所有 AI ID
    ai_ids_result = await db.execute(
        select(ChatMessage.ai_id)
        .where(ChatMessage.user_id == current_user.id)
        .distinct()
    )
    ai_ids = [row[0] for row in ai_ids_result.all()]

    if not ai_ids:
        return []

    # 加载 AI 人格信息
    personas_result = await db.execute(
        select(AIPersona).where(AIPersona.id.in_(ai_ids))
    )
    persona_map = {p.id: p for p in personas_result.scalars().all()}

    # 加载交互记录获取亲密度
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

        # 获取最后一条消息
        last_msg_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == current_user.id, ChatMessage.ai_id == ai_id)
            .order_by(ChatMessage.id.desc())
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        # 统计未读消息（AI 发送的未投递主动私信）
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

    # 按最后消息时间降序排列
    conversations.sort(key=lambda c: c.last_message_at, reverse=True)
    return conversations


# ── GET /unread-count 获取未读数 ───────────────────────────────────────────

@router.get("/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取跨所有 AI 对话的总未读消息数。

    Args:
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 包含 unread_count 的字典
    """
    result = await db.execute(
        select(func.count(ChatMessage.id))
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.role == "assistant",
            ChatMessage.delivered == 0,
        )
    )
    return {"unread_count": result.scalar() or 0}


# ── POST /mark-read/{ai_id} 标记已读 ────────────────────────────────────

@router.post("/mark-read/{ai_id}")
async def mark_conversation_read(
    ai_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    标记与指定 AI 的对话为已读。

    将所有未投递的消息标记为已投递。

    Args:
        ai_id: AI 人格 ID
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 成功消息
    """
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


# ── DELETE /messages/{id} 删除消息 ───────────────────────────────────────

@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    删除单条消息。

    用户只能删除自己对话中的消息。

    Args:
        message_id: 消息 ID
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 成功消息

    Raises:
        HTTPException: 消息不存在时返回 404 错误
    """
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


# ── GET /history/{ai_id} 获取聊天历史 ───────────────────────────────────────

@router.get("/history/{ai_id}", response_model=HistoryResponse)
async def get_chat_history(
    ai_id: int,
    limit: int = Query(default=30, ge=1, le=100),
    before_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取与指定 AI 的聊天历史（分页）。

    使用游标分页，支持向前加载更早的消息。
    同时会标记所有未投递的消息为已投递。
    如果是首次聊天（无历史消息），自动生成 AI 欢迎消息。

    Args:
        ai_id: AI 人格 ID
        limit: 返回数量上限（默认 30，最大 100）
        before_id: 游标 ID，获取此 ID 之前的消息
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        HistoryResponse: 包含消息列表和是否有更多的标志
    """
    # 检查是否是首次聊天（且不是分页加载）
    is_first_chat = False
    if before_id is None:
        is_first_chat = await chat_service.check_is_first_chat(
            db, current_user.id, ai_id
        )

    # 如果是首次聊天，生成欢迎消息
    if is_first_chat:
        # 获取 AI 人格信息
        persona_result = await db.execute(
            select(AIPersona).where(AIPersona.id == ai_id)
        )
        persona = persona_result.scalar_one_or_none()

        if persona:
            # 生成欢迎消息
            welcome_content = await chat_service.generate_welcome_message(
                db, current_user, persona
            )
            # 保存欢迎消息
            welcome_msg = await chat_service.persist_message(
                db=db,
                user_id=current_user.id,
                ai_id=ai_id,
                role="assistant",
                content=welcome_content,
                message_type="chat",
                delivered=1,  # 标记为已投递，因为用户正在查看
            )
            await db.commit()

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

    # 标记未投递的消息为已投递
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


# ── WebSocket 实时聊天 ───────────────────────────────────────────────────

@router.websocket("/ws/{ai_id}")
async def websocket_chat(
    websocket: WebSocket,
    ai_id: int,
    token: str = Query(...),
):
    """
    WebSocket 实时聊天端点。

    支持双向实时消息传输。客户端需要通过 URL 查询参数传递 JWT 令牌进行认证。

    消息格式：
    - 客户端发送：{"type": "message", "data": {"text": "...", "post_context": "..."}}
    - 服务端响应：{"type": "message_saved", "data": {"message_id": ..., "timestamp": ...}}
    - 服务端响应：{"type": "ai_reply", "data": {"message_id": ..., "text": ..., "intimacy": ...}}
    - 服务端响应：{"type": "pong"}（响应 ping）
    - 服务端响应：{"type": "error", "data": {"code": ..., "detail": ...}}（错误）

    Args:
        websocket: WebSocket 连接对象
        ai_id: AI 人格 ID
        token: JWT 认证令牌
    """
    manager = get_ws_manager()
    user: User | None = None

    # 验证 WebSocket 令牌
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
                # 心跳响应
                await websocket.send_json({"type": "pong"})
            elif msg_type == "message":
                # 处理聊天消息
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
    """
    处理通过 WebSocket 接收的聊天消息。

    Args:
        websocket: WebSocket 连接对象
        user: 当前用户
        ai_id: AI 人格 ID
        data: 消息数据（包含 text 和可选的 post_context）
    """
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

    # 发送消息已保存确认
    await websocket.send_json({
        "type": "message_saved",
        "data": {
            "message_id": result.user_message_id,
            "timestamp": None,
        },
    })

    # 发送 AI 回复
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
    """
    向客户端发送错误消息。

    Args:
        websocket: WebSocket 连接对象
        code: 错误代码
        detail: 错误详情
    """
    await websocket.send_json({
        "type": "error",
        "data": {"code": code, "detail": detail},
    })