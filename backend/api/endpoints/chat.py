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
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
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
from models.emotion_state import EmotionState
from models.virtual_gift import VirtualGift
from models.gem_transaction import GemTransaction
from models.notification import Notification
from services import chat_service
from services.scene_service import scene_service

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


# ── POST /{persona_id}/media 多模态媒体上传 ──────────────────────

# 允许上传的文件扩展名（按媒体类型划分）
_ALLOWED_MEDIA_EXTS = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
    "voice": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".webm"},
    "video": {".mp4", ".mov", ".webm"},
}
# 单个媒体文件最大上传体积（字节）
_MAX_MEDIA_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

# chat_media 绝对路径（与 main.py 挂载的 /static 一致）
_CHAT_MEDIA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "chat_media"


class MediaUploadResponse(BaseModel):
    """多模态上传响应模型。"""
    reply: str
    intimacy: float
    user_message_id: int
    ai_message_id: int
    media_type: str
    media_url: str
    voice_url: str | None = None
    nickname_proposal: dict | None = None
    emotion_hint: dict | None = None


@router.post("/{persona_id}/media", response_model=MediaUploadResponse)
async def upload_chat_media(
    persona_id: int,
    file: UploadFile = File(...),
    media_type: str = Form(...),
    caption: str = Form(""),
    generate_voice_reply: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    上传媒体文件（图片/语音/视频）并获取 AI 角色的多模态回复。

    处理流程：
    1. 验证 media_type 与文件扩展名、大小。
    2. 保存文件到 backend/static/chat_media/{media_type}/...
    3. 调用 chat_service.handle_media_message() 路由到 vision/voice 服务。
    4. 返回 AI 回复（含可选语音 URL）。

    Args:
        persona_id: AI 角色 ID
        file: 上传的媒体文件
        media_type: "image" / "voice" / "video"
        caption: 随媒体附带的文本（可选）
        generate_voice_reply: 是否同时生成 AI 语音回复
        current_user: 当前认证用户
        db: 异步数据库会话
    """
    # ── 参数验证 ─────────────────────────────────────
    if media_type not in _ALLOWED_MEDIA_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid media_type: {media_type}. Allowed: image/voice/video",
        )

    # 获取扩展名
    filename = file.filename or ""
    ext = Path(filename).suffix.lower() if filename else ""
    if ext not in _ALLOWED_MEDIA_EXTS[media_type]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File extension '{ext}' not allowed for {media_type}. "
                f"Allowed: {sorted(_ALLOWED_MEDIA_EXTS[media_type])}"
            ),
        )

    # 读取并验证文件大小
    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(contents) > _MAX_MEDIA_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large (max {_MAX_MEDIA_SIZE_BYTES} bytes)",
        )

    # ── 保存到本地静态目录 ────────────────────────────────
    target_dir = _CHAT_MEDIA_DIR / media_type
    target_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    safe_name = f"{current_user.id}_{ts}_{uuid.uuid4().hex[:8]}{ext}"
    fpath = target_dir / safe_name
    try:
        with open(fpath, "wb") as f:
            f.write(contents)
    except Exception as e:
        logger.exception("Failed to save uploaded media")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    rel_url = f"/static/chat_media/{media_type}/{safe_name}"

    # ── 路由到多模态服务 ──────────────────────────────────
    try:
        result = await chat_service.handle_media_message(
            db=db,
            user=current_user,
            ai_id=persona_id,
            media_type=media_type,
            media_url=rel_url,
            caption=caption,
            generate_voice_reply=generate_voice_reply,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        logger.exception(
            "Media handler error for user_id=%d persona_id=%d",
            current_user.id, persona_id,
        )
        raise HTTPException(status_code=500, detail="Failed to process media")

    return MediaUploadResponse(
        reply=result.reply,
        intimacy=result.intimacy,
        user_message_id=result.user_message_id,
        ai_message_id=result.ai_message_id,
        media_type=media_type,
        media_url=rel_url,
        voice_url=result.voice_url,
        nickname_proposal=result.nickname_proposal,
        emotion_hint=result.emotion_hint,
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


# ── 场景系统端点 (Plan Task 3) ────────────────────────────────────────

class SceneChoiceRequest(BaseModel):
    """交互式场景选择请求体。"""
    choice_key: str


@router.get("/scenes/{persona_id}")
async def list_available_scenes(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定角色可用的对话场景列表。

    返回项会根据用户与该角色的亲密度、解锁状态标记 ``available`` 及
    ``locked_reason``，以供前端渲染场景选择器。
    """
    persona_result = await db.execute(
        select(AIPersona).where(AIPersona.id == persona_id)
    )
    if persona_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Persona not found")

    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id == persona_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    intimacy_score = float(interaction.intimacy_score) if interaction else 0.0

    scenes = await scene_service.get_available_scenes(
        db=db,
        persona_id=persona_id,
        user_id=current_user.id,
        intimacy_score=intimacy_score,
    )
    return {
        "persona_id": persona_id,
        "intimacy_score": intimacy_score,
        "scenes": scenes,
    }


@router.post("/scenes/{persona_id}/{scene_id}/start")
async def start_scene(
    persona_id: int,
    scene_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启动一个场景会话。验证访问权限后返回初始上下文。"""
    try:
        context = await scene_service.start_scene(
            db=db,
            user_id=current_user.id,
            persona_id=persona_id,
            scene_id=scene_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return context


@router.post("/scenes/{persona_id}/end")
async def end_scene(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """结束 / 放弃当前激活场景。"""
    await scene_service.abandon_scene(
        db=db,
        user_id=current_user.id,
        persona_id=persona_id,
    )
    return {"message": "Scene ended"}


@router.get("/scenes/{persona_id}/active")
async def get_active_scene(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前激活场景上下文（如果有）。"""
    context = await scene_service.get_active_scene_context(
        db=db,
        user_id=current_user.id,
        persona_id=persona_id,
    )
    return {"active_scene": context}


@router.post("/scenes/{persona_id}/choice")
async def make_scene_choice(
    persona_id: int,
    body: SceneChoiceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """记录用户在交互式场景中选择的分支。"""
    try:
        await scene_service.record_choice(
            db=db,
            user_id=current_user.id,
            persona_id=persona_id,
            choice_key=body.choice_key,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"message": "Choice recorded", "choice_key": body.choice_key}


# ── 用户发起交互变种与留存机制端点 (Plan Task 6) ─────────────────────

import re

from services.aliyun_ai_service import generate_proactive_dm, generate_image_prompt

# Streak 里程碑配置——与 emotion_scheduler.py 中一致
_STREAK_MILESTONE_TABLE: dict[int, dict] = {
    7:   {"intimacy_bonus": 3,  "gems": 10,  "message": "连续7天的陪伴"},
    14:  {"intimacy_bonus": 5,  "gems": 20,  "message": "两周了"},
    30:  {"intimacy_bonus": 10, "gems": 50,  "message": "一个月的默契"},
    60:  {"intimacy_bonus": 15, "gems": 100, "message": "60天"},
    100: {"intimacy_bonus": 25, "gems": 200, "message": "100天纪念"},
}

_TIME_HHMM_RE = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")

# 自拍请求所需能量阈值
_SELFIE_ENERGY_COST = 10


async def _get_or_create_interaction(
    db: AsyncSession, user_id: int, ai_id: int,
) -> Interaction:
    """读取 (user_id, ai_id) 对应的 Interaction，不存在则创建。"""
    result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == user_id,
            Interaction.ai_id == ai_id,
        )
    )
    interaction = result.scalar_one_or_none()
    if interaction is None:
        interaction = Interaction(user_id=user_id, ai_id=ai_id)
        db.add(interaction)
        await db.flush()
    return interaction


@router.post("/{persona_id}/request-selfie")
async def request_selfie(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """用户请求 AI 角色发一张自拍。消耗角色能量，返回生成的图片 URL 与反应文本。

    流程：
        1. 检查当前 (user, persona) 的 EmotionState.energy >= 10。
        2. 获取当前情绪 + 激活服装。
        3. 使用面部参考图生成 anime 风格自拍。
        4. 创建 media_type="image" 的 ChatMessage。
        5. 从 EmotionState 扣除能量并轻微提升愉悦。
    """
    # 加载角色
    persona_res = await db.execute(
        select(AIPersona).where(AIPersona.id == persona_id)
    )
    persona = persona_res.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")

    # 加载情绪状态
    emo_res = await db.execute(
        select(EmotionState).where(
            EmotionState.user_id == current_user.id,
            EmotionState.ai_id == persona_id,
        )
    )
    state = emo_res.scalar_one_or_none()
    if state is None or state.energy is None or state.energy < _SELFIE_ENERGY_COST:
        raise HTTPException(
            status_code=400,
            detail=f"Persona is too tired to take a selfie (need >= {_SELFIE_ENERGY_COST} energy)",
        )

    # 补充当前情绪描述
    if state.pleasure > 0.4:
        mood_expression = "soft genuine smile, eyes bright, warm gaze"
    elif state.pleasure < -0.2:
        mood_expression = "thoughtful expression, quiet eyes, slight melancholy"
    else:
        mood_expression = "calm relaxed expression, soft natural look"

    # 读取当前激活服装（可能为 None）
    outfit_override = None
    try:
        from services.image_gen_service import get_active_outfit
        outfit_override = await get_active_outfit(
            db,
            persona_id=persona.id,
            emotion_state={
                "pleasure": state.pleasure,
                "activation": state.activation,
                "energy": state.energy,
            },
        )
    except Exception as exc:
        logger.warning("Outfit lookup for selfie failed: %s", exc)

    # 生成场景提示词（为“自拍”固化一些描述）
    selfie_caption = (
        f"casual selfie taken on phone, slight angle from above, "
        f"{mood_expression}, soft natural lighting"
    )
    try:
        img_prompt = await generate_image_prompt(
            persona_prompt=persona.personality_prompt,
            style_tags=persona.ins_style_tags,
            caption=selfie_caption,
            visual_description=getattr(persona, "visual_prompt_tags", None),
            persona_name=persona.name,
        )
    except Exception as exc:
        logger.warning("Selfie prompt generation failed: %s", exc)
        img_prompt = selfie_caption

    # 生成图片
    media_url = ""
    base_face_url = getattr(persona, "base_face_url", None)
    try:
        from services.image_gen_service import (
            generate_image_with_face_ref,
            generate_image,
            download_to_static,
        )
        if base_face_url:
            urls = await generate_image_with_face_ref(
                prompt=img_prompt,
                face_ref_url=base_face_url,
                size="720*1280",
                n=1,
                persona_id=persona.id,
                outfit_override=outfit_override,
            )
        else:
            urls = await generate_image(
                prompt=img_prompt,
                n=1,
                persona_id=persona.id,
                outfit_override=outfit_override,
            )
        if urls:
            media_url = await download_to_static(urls[0], prefix=f"selfie_{persona.id}")
    except Exception as exc:
        logger.exception("Selfie generation failed: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to generate selfie")

    if not media_url:
        raise HTTPException(status_code=500, detail="Selfie image unavailable")

    # 生成 AI 反应文本
    try:
        reaction_text = await generate_proactive_dm(
            persona_prompt=persona.personality_prompt,
            system_instruction=(
                "The user just asked for a selfie. Send a short in-character reply "
                "(1–2 sentences) acknowledging the photo. Stay natural, no narration. "
                "Reply ONLY with the message text."
            ),
            temperature=0.85,
            max_tokens=120,
        )
    except Exception as exc:
        logger.warning("Selfie reaction text failed: %s", exc)
        reaction_text = "拍了一张给你。"

    # 扣除能量，轻微提升愉悦
    state.energy = max(0.0, state.energy - _SELFIE_ENERGY_COST)
    state.pleasure = max(-1.0, min(1.0, state.pleasure + 0.03))

    # 写入聊天消息（AI 贴出自拍）
    chat_msg = ChatMessage(
        user_id=current_user.id,
        ai_id=persona_id,
        role="assistant",
        content=reaction_text,
        message_type="chat",
        media_type="image",
        media_url=media_url,
        event="selfie",
        delivered=1,
    )
    db.add(chat_msg)
    await db.commit()
    await db.refresh(chat_msg)

    return {
        "message_id": chat_msg.id,
        "media_url": media_url,
        "reaction": reaction_text,
        "energy_remaining": state.energy,
    }


class GiftSendResponse(BaseModel):
    gift_id: int
    gift_name: str
    gems_spent: int
    gems_remaining: int
    energy_recovered: float
    reaction: str
    combo_count: int
    combo_triggered: bool
    scene_triggered: bool
    message_id: int


@router.post("/{persona_id}/send-gift-enhanced", response_model=GiftSendResponse)
async def send_gift_enhanced(
    persona_id: int,
    gift_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """增强版送礼物：含 AI 在场反应 + 连击检测 + 特殊场景触发。

    流程：
        1. 验证用户钻石。
        2. 扣费 + 写 GemTransaction。
        3. 应用能量恢复到 AI 情绪状态。
        4. 生成在场反应文本（优先用 gift.reaction_template）。
        5. 连击：最近 5 分钟同口 gift、计数 >= combo_bonus_threshold/3，推送加能量奖励。
        6. 若 gift.triggers_scene，尝试启动一个与 gift 同名场景。
    """
    # 加载角色 + 礼物
    persona = (await db.execute(
        select(AIPersona).where(AIPersona.id == persona_id)
    )).scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")

    gift = (await db.execute(
        select(VirtualGift).where(VirtualGift.id == gift_id, VirtualGift.is_active == 1)
    )).scalar_one_or_none()
    if gift is None:
        raise HTTPException(status_code=404, detail="Gift not found or inactive")

    # 检查钻石余额
    if int(current_user.gem_balance or 0) < int(gift.gem_cost):
        raise HTTPException(status_code=400, detail="Insufficient gem balance")

    # 扣费
    current_user.gem_balance = int(current_user.gem_balance or 0) - int(gift.gem_cost)
    db.add(GemTransaction(
        user_id=current_user.id,
        amount=-int(gift.gem_cost),
        balance_after=current_user.gem_balance,
        tx_type="gift_send",
        reference_id=f"gift_{gift.id}_persona_{persona.id}",
        description=f"Sent gift '{gift.name}' to {persona.name}",
    ))

    # 应用能量恢复到 AI 情绪状态
    state = (await db.execute(
        select(EmotionState).where(
            EmotionState.user_id == current_user.id,
            EmotionState.ai_id == persona_id,
        )
    )).scalar_one_or_none()
    if state is not None and gift.energy_recovery:
        state.energy = min(100.0, float(state.energy or 0.0) + float(gift.energy_recovery))
        state.pleasure = max(-1.0, min(1.0, float(state.pleasure or 0.0) + 0.05))

    # 连击检测：最近 5 分钟同一 gift 计数（含本次）
    from datetime import timedelta as _td
    from datetime import datetime as _dt
    cutoff = _dt.utcnow() - _td(minutes=5)
    await db.flush()  # 确保本次 GemTransaction 被计入
    combo_count_q = await db.execute(
        select(func.count(GemTransaction.id)).where(
            GemTransaction.user_id == current_user.id,
            GemTransaction.tx_type == "gift_send",
            GemTransaction.reference_id == f"gift_{gift.id}_persona_{persona.id}",
            GemTransaction.created_at >= cutoff,
        )
    )
    combo_count = int(combo_count_q.scalar() or 0)
    combo_threshold = int(gift.combo_bonus_threshold or 3)
    combo_triggered = combo_count >= combo_threshold

    if combo_triggered and state is not None:
        # 额外能量 + 愉悦奖励
        state.energy = min(100.0, float(state.energy) + 5.0)
        state.pleasure = max(-1.0, min(1.0, float(state.pleasure) + 0.1))

    # 生成在场反应
    base_directive = (
        gift.reaction_template
        or f"You just received a gift '{gift.name}' from this person. "
        "React in-character with warmth and acknowledgement."
    )
    combo_directive = (
        f"\nThey have sent you {combo_count} of '{gift.name}' in the last 5 minutes. "
        "Reference this gentle combo / abundance in your reply."
        if combo_triggered else ""
    )
    try:
        reaction = await generate_proactive_dm(
            persona_prompt=persona.personality_prompt,
            system_instruction=(
                f"{base_directive}{combo_directive}\n"
                "Reply ONLY with the message text (1–2 sentences). Stay in character."
            ),
            temperature=0.85,
            max_tokens=160,
        )
    except Exception as exc:
        logger.warning("Gift reaction generation failed: %s", exc)
        reaction = f"谢谢你的{gift.name}。"

    # 写 ChatMessage
    chat_msg = ChatMessage(
        user_id=current_user.id,
        ai_id=persona_id,
        role="assistant",
        content=reaction,
        message_type="chat",
        event=f"gift_{gift.id}",
        delivered=1,
    )
    db.add(chat_msg)
    await db.flush()

    # 场景触发：查找同名场景并尝试启动
    scene_triggered = False
    if gift.triggers_scene:
        try:
            from models.chat_scene import ChatScene
            scene_res = await db.execute(
                select(ChatScene).where(
                    ChatScene.persona_id == persona.id,
                    ChatScene.scene_name == gift.name,
                    ChatScene.is_active == True,  # noqa: E712
                ).limit(1)
            )
            target_scene = scene_res.scalar_one_or_none()
            if target_scene is not None:
                try:
                    await scene_service.start_scene(
                        db=db,
                        user_id=current_user.id,
                        persona_id=persona.id,
                        scene_id=target_scene.id,
                    )
                    scene_triggered = True
                except ValueError as scene_exc:
                    logger.info(
                        "Gift scene start skipped: %s", scene_exc,
                    )
        except Exception as exc:
            logger.warning("Gift scene trigger lookup failed: %s", exc)

    await db.commit()
    await db.refresh(chat_msg)

    return GiftSendResponse(
        gift_id=gift.id,
        gift_name=gift.name,
        gems_spent=int(gift.gem_cost),
        gems_remaining=int(current_user.gem_balance),
        energy_recovered=float(gift.energy_recovery or 0.0),
        reaction=reaction,
        combo_count=combo_count,
        combo_triggered=combo_triggered,
        scene_triggered=scene_triggered,
        message_id=chat_msg.id,
    )


class RitualConfigBody(BaseModel):
    morning_greeting: bool | None = None
    morning_time: str | None = None
    night_greeting: bool | None = None
    night_time: str | None = None
    mood_checkin: bool | None = None
    shared_habit: str | None = None


@router.post("/{persona_id}/configure-rituals")
async def configure_rituals(
    persona_id: int,
    config: RitualConfigBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """配置用户与某角色的每日仪式偏好。

    只会合并传入的字段，所以前端可以留。None 表示保持原值。时间需为 HH:MM。
    """
    # 验证角色存在
    persona = (await db.execute(
        select(AIPersona).where(AIPersona.id == persona_id)
    )).scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")

    # 验证时间格式
    for label, value in (("morning_time", config.morning_time), ("night_time", config.night_time)):
        if value is not None and not _TIME_HHMM_RE.match(value):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {label} format, expected HH:MM (00–23 : 00–59)",
            )

    interaction = await _get_or_create_interaction(db, current_user.id, persona_id)
    existing = dict(interaction.ritual_config_json or {})
    incoming = config.model_dump(exclude_unset=True, exclude_none=True)
    existing.update(incoming)
    interaction.ritual_config_json = existing

    await db.commit()
    return {
        "persona_id": persona_id,
        "ritual_config": existing,
    }


@router.get("/{persona_id}/streak")
async def get_streak_info(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前 streak 信息与下一个里程碑。"""
    persona = (await db.execute(
        select(AIPersona).where(AIPersona.id == persona_id)
    )).scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=404, detail="Persona not found")

    interaction = (await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id == persona_id,
        )
    )).scalar_one_or_none()

    current_streak = int(interaction.streak_count or 0) if interaction else 0
    total_days = int(interaction.total_interaction_days or 0) if interaction else 0
    last_streak_date = interaction.last_streak_date if interaction else None

    sorted_milestones = sorted(_STREAK_MILESTONE_TABLE.keys())
    next_milestone = next(
        (m for m in sorted_milestones if m > current_streak),
        None,
    )
    next_reward = _STREAK_MILESTONE_TABLE.get(next_milestone) if next_milestone else None

    return {
        "persona_id": persona_id,
        "current_streak": current_streak,
        "total_days": total_days,
        "last_streak_date": last_streak_date,
        "next_milestone": next_milestone,
        "next_milestone_reward": next_reward,
    }