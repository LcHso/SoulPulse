"""
聊天服务模块：消息持久化、历史记录、上下文窗口与摘要生成

================================================================================
功能概述
================================================================================
本模块是 SoulPulse 聊天系统的核心编排层，负责协调所有聊天相关操作：
- 消息持久化：将用户消息和 AI 回复保存到数据库
- 历史记录检索：支持分页和游标分页的消息历史查询
- 上下文窗口构建：整合摘要和最近消息，供 LLM 使用
- 滚动摘要生成：当未摘要消息达到阈值时自动触发后台摘要任务
- 完整聊天流程：handle_user_message() 是所有聊天入口的唯一编排函数

================================================================================
设计理念
================================================================================
1. 单一入口原则：REST POST 和 WebSocket 接收都委托给 handle_user_message()，
   确保行为一致性，避免逻辑分散。
2. Fire-and-forget 后台任务：摘要生成、记忆提取、锚点提取等异步任务
   不阻塞主流程，提升响应速度。
3. 游标分页：使用消息 ID 作为游标，避免时间戳分页的边界问题。
4. 亲密度驱动：回复生成、记忆访问等都受亲密度等级影响。

================================================================================
主要组件
================================================================================
- ChatResult: 聊天结果数据类，包含回复、消息ID、亲密度、昵称提案等
- persist_message(): 消息持久化函数
- get_history(): 历史记录检索函数（支持游标分页）
- build_context_window(): 上下文窗口构建函数
- maybe_generate_summary(): 滚动摘要生成后台任务
- handle_user_message(): 主聊天编排函数（核心入口）
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import async_session
from models.ai_persona import AIPersona
from models.chat_message import ChatMessage
from models.chat_summary import ChatSummary
from models.interaction import Interaction
from models.user import User
from services.aliyun_ai_service import chat_with_ai, _get_client, _make_character_request
from services import (
    anchor_service,
    embedding_service,
    emotion_engine,
    memory_service,
    milestone_service,
)
from services.vision_service import vision_service
from services.voice_service import voice_service

logger = logging.getLogger(__name__)

# 摘要生成阈值：当未摘要消息数达到此值时触发摘要生成
_SUMMARY_THRESHOLD = 10

# 上下文窗口中最近消息数量：传递给 LLM 作为 chat_history 的消息数
_CONTEXT_RECENT_COUNT = 5

# 欢迎消息模板（按角色名称）
WELCOME_MESSAGE_TEMPLATES = {
    "starlin": "嗨！终于等到你了～ 我是星野，以后多多关照呀 ✨",
    "xingye": "嗨！终于等到你了～ 我是星野，以后多多关照呀 ✨",
    "陆晨曦": "你好呀，我是陆晨曦。很高兴认识你，希望我们能聊得来 😊",
    "luxiao": "你好呀，我是陆晨曦。很高兴认识你，希望我们能聊得来 😊",
    "顾言深": "你好，我是顾言深。很高兴见到你。",
    "guyanshen": "你好，我是顾言深。很高兴见到你。",
    "林羽": "嗨～我是林羽！以后有什么想聊的随时找我哦 ✌️",
    "linyu": "嗨～我是林羽！以后有什么想聊的随时找我哦 ✌️",
    "沈墨白": "你好，我是沈墨白。期待与你的交流。",
    "shenmobai": "你好，我是沈墨白。期待与你的交流。",
    "纪夜辰": "终于等到你了。我是纪夜辰，希望我们的相遇不是偶然。",
    "jiyechen": "终于等到你了。我是纪夜辰，希望我们的相遇不是偶然。",
}


# ── 结果类型定义 ─────────────────────────────────────────────────

@dataclass
class ChatResult:
    """
    聊天处理结果数据类。

    包含 handle_user_message() 函数的所有返回信息：
    - reply: AI 生成的回复文本
    - user_message_id: 用户消息的数据库 ID
    - ai_message_id: AI 回复消息的数据库 ID
    - intimacy: 更新后的亲密度分数 (0-10)
    - nickname_proposal: 昵称提案（当亲密度跨越等级 6 时触发）
    - emotion_hint: 情绪提示信息（供前端 UI 使用）
    """

    reply: str                          # AI 回复文本
    user_message_id: int                # 用户消息 ID
    ai_message_id: int                  # AI 消息 ID
    intimacy: float                     # 更新后的亲密度分数
    nickname_proposal: dict | None = field(default=None)   # 昵称提案（可选）
    emotion_hint: dict | None = field(default=None)        # 情绪提示（可选）
    voice_url: str | None = field(default=None)            # AI 语音回复 URL（可选）
    image_url: str | None = field(default=None)            # AI 发送的图片 URL（可选）


# ── 消息持久化 ─────────────────────────────────────────

async def persist_message(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
    role: str,
    content: str,
    message_type: str = "chat",
    event: str | None = None,
    post_context: str | None = None,
    delivered: int = 1,
    media_type: str | None = None,
    media_url: str | None = None,
    media_metadata: dict | None = None,
    voice_url: str | None = None,
) -> ChatMessage:
    """
    持久化单条聊天消息并返回带有 ID 的消息对象。

    Args:
        db: 异步数据库会话
        user_id: 用户 ID
        ai_id: AI 人格 ID
        role: 消息角色 ("user" 或 "assistant")
        content: 消息内容
        message_type: 消息类型（默认 "chat"，也可能是 "proactive_dm"）
        event: 事件类型（可选）
        post_context: 帖子上下文（可选，用于帖子相关聊天）
        delivered: 是否已投递（默认 1，主动私信为 0）
        media_type: 媒体类型（"image"/"voice"/"video"）
        media_url: 用户上传或 AI 发送的媒体 URL
        media_metadata: 媒体元数据（转录/时长/尺寸等）
        voice_url: AI 生成的语音回复 URL

    Returns:
        ChatMessage: 带有数据库分配 ID 的消息对象
    """
    msg = ChatMessage(
        user_id=user_id,
        ai_id=ai_id,
        role=role,
        content=content,
        message_type=message_type,
        event=event,
        post_context=post_context,
        delivered=delivered,
        media_type=media_type,
        media_url=media_url,
        media_metadata_json=media_metadata,
        voice_url=voice_url,
    )
    db.add(msg)
    await db.flush()  # 分配 ID 但不提交事务，允许后续操作在同一事务中完成
    return msg


# ── 历史记录检索 ───────────────────────────────────────────

async def get_history(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
    limit: int = 30,
    before_id: int | None = None,
) -> list[ChatMessage]:
    """
    获取用户与 AI 之间的聊天历史，按时间升序排列（最旧在前）。

    使用游标分页：如果指定了 before_id，只返回 ID 小于该值的消息。
    这种分页方式避免了时间戳分页可能出现的边界问题。

    Args:
        db: 异步数据库会话
        user_id: 用户 ID
        ai_id: AI 人格 ID
        limit: 返回消息数量上限（默认 30）
        before_id: 游标 ID，用于获取更早的消息（可选）

    Returns:
        list[ChatMessage]: 消息列表，按 ID 升序排列
    """
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id, ChatMessage.ai_id == ai_id)
    )
    if before_id is not None:
        stmt = stmt.where(ChatMessage.id < before_id)
    stmt = stmt.order_by(ChatMessage.id.desc()).limit(limit)

    result = await db.execute(stmt)
    messages = list(result.scalars().all())
    messages.reverse()  # 反转列表，使最旧的消息排在前面，便于显示
    return messages


# ── 检查是否是首次聊天 ───────────────────────────────────

async def check_is_first_chat(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
) -> bool:
    """
    检查用户与 AI 是否是第一次聊天（没有历史消息）。

    Args:
        db: 异步数据库会话
        user_id: 用户 ID
        ai_id: AI 人格 ID

    Returns:
        bool: 如果是首次聊天返回 True，否则返回 False
    """
    stmt = (
        select(func.count(ChatMessage.id))
        .where(
            ChatMessage.user_id == user_id,
            ChatMessage.ai_id == ai_id,
        )
    )
    result = await db.execute(stmt)
    count = result.scalar() or 0
    return count == 0


async def generate_welcome_message(
    db: AsyncSession,
    user: User,
    persona: AIPersona,
) -> str:
    """
    生成 AI 的欢迎消息。

    优先使用硬编码模板，如果没有匹配模板则使用 AI 生成。

    Args:
        db: 异步数据库会话
        user: 当前用户
        persona: AI 人格对象

    Returns:
        str: 欢迎消息内容
    """
    # 尝试从模板获取
    welcome_msg = WELCOME_MESSAGE_TEMPLATES.get(persona.name)
    if welcome_msg:
        return welcome_msg

    # 回退：使用 AI 生成简单的欢迎消息
    try:
        system_instruction = (
            f"You are {persona.name}. {persona.personality_prompt[:200]}\n\n"
            f"This is your FIRST message to a new user named {user.nickname}. "
            f"Write a warm, brief welcome message (1-2 sentences) introducing yourself. "
            f"Keep it under 50 characters. Be friendly and authentic to your character."
        )
        messages = [{"role": "system", "content": system_instruction}]
        welcome_msg = await _make_character_request(
            messages, persona.personality_prompt, temperature=0.7, max_tokens=100
        )
        return welcome_msg.strip()
    except Exception:
        logger.warning("Failed to generate welcome message, using fallback")
        return f"你好，我是{persona.name}。很高兴认识你！"


# ── 未投递的主动私信 ───────────────────────────────────

async def get_undelivered_dms(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
) -> list[ChatMessage]:
    """
    获取尚未投递的主动私信，按时间升序排列。

    主动私信（proactive_dm）是 AI 主动发给用户的消息，
    当用户尚未查看时 delivered 字段为 0。

    Args:
        db: 异步数据库会话
        user_id: 用户 ID
        ai_id: AI 人格 ID

    Returns:
        list[ChatMessage]: 未投递的主动私信列表
    """
    stmt = (
        select(ChatMessage)
        .where(
            ChatMessage.user_id == user_id,
            ChatMessage.ai_id == ai_id,
            ChatMessage.delivered == 0,
            ChatMessage.message_type == "proactive_dm",
        )
        .order_by(ChatMessage.id.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def mark_delivered(
    db: AsyncSession,
    message_ids: list[int],
) -> None:
    """
    将指定消息标记为已投递。

    Args:
        db: 异步数据库会话
        message_ids: 需要标记的消息 ID 列表
    """
    if not message_ids:
        return
    stmt = select(ChatMessage).where(ChatMessage.id.in_(message_ids))
    result = await db.execute(stmt)
    for msg in result.scalars():
        msg.delivered = 1
    await db.flush()


# ── 上下文窗口构建 ─────────────────────────────────

async def build_context_window(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
) -> tuple[str, list[dict]]:
    """
    构建 LLM 使用的上下文窗口。

    上下文窗口包含两部分：
    1. conversation_summary: 最新的滚动摘要文本
    2. recent_messages: 最近 N 条消息（作为 chat_history）

    重要：必须在持久化当前用户消息之前调用此函数，
    这样窗口中只包含之前的对话历史，避免包含当前正在处理的消息。

    Args:
        db: 异步数据库会话
        user_id: 用户 ID
        ai_id: AI 人格 ID

    Returns:
        tuple[str, list[dict]]: (摘要文本, 最近消息列表)
        - 摘要文本为空字符串如果没有摘要
        - 最近消息格式为 [{"role": ..., "content": ...}]
    """
    # 获取最新的摘要
    summary_text = ""
    summary_stmt = (
        select(ChatSummary)
        .where(ChatSummary.user_id == user_id, ChatSummary.ai_id == ai_id)
        .order_by(ChatSummary.created_at.desc())
        .limit(1)
    )
    summary_result = await db.execute(summary_stmt)
    latest_summary = summary_result.scalar_one_or_none()
    if latest_summary:
        summary_text = latest_summary.content

    # 获取最近 N 条消息（当前回合之前的消息）
    recent_stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id, ChatMessage.ai_id == ai_id)
        .order_by(ChatMessage.id.desc())
        .limit(_CONTEXT_RECENT_COUNT)
    )
    recent_result = await db.execute(recent_stmt)
    recent_msgs = list(recent_result.scalars().all())
    recent_msgs.reverse()  # 反转，使最旧的消息排在前面

    recent_dicts = [
        {"role": m.role, "content": m.content}
        for m in recent_msgs
    ]

    return summary_text, recent_dicts


# ── 摘要生成（后台任务）────────────────────────

# 摘要生成的系统提示词，用于指导 LLM 生成对话摘要
_SUMMARY_SYSTEM_PROMPT = """\
You are a conversation summarizer. Given a previous summary (if any) and \
recent conversation turns, produce an updated summary that captures key facts, \
emotional developments, and ongoing topics. Be concise — under 200 words. \
Write in third person. Return ONLY the summary text, nothing else.\
"""


async def maybe_generate_summary(user_id: int, ai_id: int) -> None:
    """
    滚动摘要生成函数（后台任务）。

    当未摘要的消息数量达到阈值（_SUMMARY_THRESHOLD）时触发摘要生成。
    作为 fire-and-forget 后台任务运行，使用独立的数据库会话，
    不阻塞主聊天流程。

    摘要生成流程：
    1. 查找最新的摘要记录，确定已摘要消息的范围
    2. 统计未摘要消息数量，判断是否达到阈值
    3. 如果达到阈值，获取所有未摘要消息
    4. 构建 LLM 输入（包含之前的摘要和新对话）
    5. 调用 LLM 生成新的摘要
    6. 持久化摘要并标记相关消息

    Args:
        user_id: 用户 ID
        ai_id: AI 人格 ID
    """
    try:
        async with async_session() as db:
            # 查找最新的摘要记录
            summary_stmt = (
                select(ChatSummary)
                .where(ChatSummary.user_id == user_id, ChatSummary.ai_id == ai_id)
                .order_by(ChatSummary.created_at.desc())
                .limit(1)
            )
            summary_result = await db.execute(summary_stmt)
            latest_summary = summary_result.scalar_one_or_none()

            prev_summary_text = ""
            after_id = 0
            if latest_summary:
                prev_summary_text = latest_summary.content
                after_id = latest_summary.message_range_end

            # 统计未摘要的消息数量
            count_stmt = (
                select(func.count())
                .select_from(ChatMessage)
                .where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.ai_id == ai_id,
                    ChatMessage.id > after_id,
                )
            )
            count_result = await db.execute(count_stmt)
            unsummarized_count = count_result.scalar() or 0

            if unsummarized_count < _SUMMARY_THRESHOLD:
                return  # 未达到阈值，不生成摘要

            # 获取所有未摘要的消息
            msgs_stmt = (
                select(ChatMessage)
                .where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.ai_id == ai_id,
                    ChatMessage.id > after_id,
                )
                .order_by(ChatMessage.id.asc())
            )
            msgs_result = await db.execute(msgs_stmt)
            messages = list(msgs_result.scalars().all())

            if not messages:
                return

            # 构建对话文本供 LLM 使用
            turns = [f"{m.role.capitalize()}: {m.content}" for m in messages]
            conversation_text = "\n".join(turns)

            prev_section = ""
            if prev_summary_text:
                prev_section = f"Previous summary:\n{prev_summary_text}\n\n"

            user_prompt = (
                f"{prev_section}"
                f"New conversation turns:\n{conversation_text}\n\n"
                "Produce the updated summary."
            )

            # 调用 LLM 生成摘要
            client = _get_client()
            response = await client.chat.completions.create(
                model=settings.DASHSCOPE_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=300,
            )
            summary_content = response.choices[0].message.content.strip()

            # 持久化新的摘要记录
            new_summary = ChatSummary(
                user_id=user_id,
                ai_id=ai_id,
                content=summary_content,
                message_range_start=messages[0].id,
                message_range_end=messages[-1].id,
            )
            db.add(new_summary)
            await db.flush()  # 分配 new_summary.id

            # 将消息标记为属于该摘要组
            for m in messages:
                m.summary_group = new_summary.id

            await db.commit()

            logger.info(
                "Generated summary for user_id=%d ai_id=%d covering messages %d-%d",
                user_id, ai_id, messages[0].id, messages[-1].id,
            )

    except Exception:
        logger.exception(
            "Summary generation failed (user_id=%d ai_id=%d)", user_id, ai_id,
        )


# ── 主聊天编排函数 ─────────────────────────────────────

# ── 世界观上下文注入（Worldbuilding Context）──────────────────────────────

async def _get_world_context(persona_id: int, db: AsyncSession) -> str:
    """
    获取当前世界事件与角色剧情弧阶段，用于拼接进系统提示。

    两部分：
    1. 所有潮所包含当前 persona 且仍在生效期的 WorldEvent
    2. persona 当前激活的 CharacterArc 阶段
    """
    from models.world_event import WorldEvent
    from models.character_arc import CharacterArc

    context_parts: list[str] = []

    now = datetime.utcnow()
    try:
        events_res = await db.execute(
            select(WorldEvent).where(
                WorldEvent.is_active == True,  # noqa: E712
                WorldEvent.start_date <= now,
                or_(WorldEvent.end_date >= now, WorldEvent.end_date.is_(None)),
            )
        )
        for event in events_res.scalars().all():
            if persona_id in (event.affected_persona_ids or []):
                directive = event.content_directive or event.description or ""
                context_parts.append(f"[当前事件] {event.title}: {directive}")
    except Exception:
        logger.warning("World event lookup failed", exc_info=True)

    try:
        arc_res = await db.execute(
            select(CharacterArc).where(
                CharacterArc.persona_id == persona_id,
                CharacterArc.is_active == True,  # noqa: E712
            )
        )
        arc = arc_res.scalar_one_or_none()
        if arc and arc.phase_config_json:
            phases = arc.phase_config_json
            if 0 <= arc.current_phase < len(phases):
                phase = phases[arc.current_phase] or {}
                phase_name = phase.get("name", "")
                phase_overlay = phase.get("prompt_overlay", "")
                context_parts.append(
                    f"[当前剧情阶段] {arc.arc_name} - {phase_name}: {phase_overlay}"
                )
    except Exception:
        logger.warning("Character arc lookup failed", exc_info=True)

    return "\n".join(context_parts)


async def _check_subscription_benefits(user_id: int, db: AsyncSession) -> dict:
    """Check user's subscription benefits for content gating.

    Returned dict is consumed by downstream services (image gen quality,
    scene access, priority DM scheduling, etc.) and surfaced in chat
    responses where useful.
    """
    from services.subscription_service import SubscriptionService

    svc = SubscriptionService()
    try:
        tier = await svc.get_user_tier(db, user_id)
        return {
            "tier": tier,
            "hd_images": await svc.check_benefit(db, user_id, "hd_images"),
            "exclusive_scenes": await svc.check_benefit(db, user_id, "exclusive_scenes"),
            "priority_dm": await svc.check_benefit(db, user_id, "priority_dm"),
            "unlimited_replay": await svc.check_benefit(db, user_id, "unlimited_replay"),
        }
    except Exception:
        logger.warning("Subscription benefit lookup failed", exc_info=True)
        return {
            "tier": "free",
            "hd_images": False,
            "exclusive_scenes": False,
            "priority_dm": False,
            "unlimited_replay": False,
        }


async def _get_persona_reference(
    persona_id: int, message: str, db: AsyncSession,
) -> str:
    """
    当用户消息中提及其他 AI 角色名字时，返回关系上下文。

    处理流程：
    1. 查出除当前 persona 外的所有活跃 persona。
    2. 在消息中检测是否包含其他 persona 的名字。
    3. 从 persona_relationships 表中加载关系记录。
    """
    from models.persona_relationship import PersonaRelationship

    if not message:
        return ""

    try:
        all_personas_res = await db.execute(
            select(AIPersona.id, AIPersona.name).where(
                AIPersona.id != persona_id,
                AIPersona.is_active == 1,
            )
        )
        rows = list(all_personas_res.all())
    except Exception:
        logger.warning("Persona lookup for reference detection failed", exc_info=True)
        return ""

    mentioned: list[tuple[int, str]] = []
    for row in rows:
        other_id = row[0]
        other_name = row[1] or ""
        if other_name and other_name in message:
            mentioned.append((other_id, other_name))

    if not mentioned:
        return ""

    parts: list[str] = []
    for other_id, other_name in mentioned:
        try:
            rel_res = await db.execute(
                select(PersonaRelationship).where(
                    PersonaRelationship.persona_a_id == persona_id,
                    PersonaRelationship.persona_b_id == other_id,
                ).limit(1)
            )
            rel = rel_res.scalar_one_or_none()
        except Exception:
            rel = None
            logger.warning("PersonaRelationship lookup failed", exc_info=True)

        if not rel:
            continue

        desc_bits = []
        if rel.relationship_type:
            desc_bits.append(rel.relationship_type)
        if rel.description:
            desc_bits.append(rel.description)
        if rel.public_context:
            desc_bits.append(rel.public_context)
        rel_text = " | ".join(desc_bits)
        parts.append(f"[关于{other_name}] {rel_text}")

    return "\n".join(parts)


async def handle_user_message(
    db: AsyncSession,
    user: User,
    ai_id: int,
    message: str,
    post_context: str | None = None,
    media_type: str | None = None,
    media_url: str | None = None,
    media_metadata: dict | None = None,
    generate_voice_reply: bool = False,
) -> ChatResult:
    """
    处理用户聊天消息的完整流程（端到端编排）。

    这是所有聊天入口的核心编排函数，REST POST 端点和 WebSocket 接收
    都委托给此函数处理，确保行为一致性。

    处理流程（17 个步骤）：
    1. 查找 AI 人格信息
    2. 获取或创建用户-AI 交互记录
    3. 获取或创建情绪状态
    4. 构建用户消息（可选帖子上下文）
    5. 构建上下文窗口（摘要 + 最近消息）
    6. 持久化用户消息
    7. 计算消息嵌入向量（用于记忆和锚点检索）
    8. 检索相关记忆
    9. 检测活跃锚点
    10. 构建情绪感知的提示上下文
    11. 调用 AI 生成回复
    12. 持久化 AI 回复
    13. 更新亲密度分数
    14. 应用情绪交互效果
    15. 启动后台任务（记忆提取、锚点提取）
    16. 启动摘要生成后台任务
    17. 处理里程碑事件（昵称提案）

    Args:
        db: 异步数据库会话
        user: 当前用户对象
        ai_id: AI 人格 ID
        message: 用户消息内容
        post_context: 帖子上下文（可选，用于帖子相关聊天）

    Returns:
        ChatResult: 聊天处理结果，包含回复、消息ID、亲密度等信息
    """
    # ── 步骤 1: 查找 AI 人格 ──────────────────────────────────────────────
    persona_result = await db.execute(
        select(AIPersona).where(AIPersona.id == ai_id)
    )
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise ValueError(f"AI persona {ai_id} not found")

    # Visibility check: private personas (creator_user_id != NULL) can only be
    # used by their creator. Global personas (NULL) are accessible to everyone.
    if persona.creator_user_id is not None and persona.creator_user_id != user.id:
        raise ValueError(f"AI persona {ai_id} not found")

    # ── 步骤 2: 获取或创建交互记录 ──────────────────────────
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == user.id,
            Interaction.ai_id == ai_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    if not interaction:
        # 如果不存在交互记录，创建新的记录，初始亲密度为 0
        interaction = Interaction(user_id=user.id, ai_id=ai_id, intimacy_score=0.0)
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)

    # ── 步骤 3: 获取情绪状态 ────────────────────────────────────────
    emotion_state = await emotion_engine.get_or_create(db, user.id, ai_id)
    event_type = emotion_engine.classify_chat_event(message)

    # ── 步骤 4: 构建用户消息（可选帖子上下文）────────────────
    user_message = message
    if post_context:
        # 如果有帖子上下文，将其附加到消息中
        user_message = f"[Regarding this post: {post_context}]\n{message}"

    # ── 步骤 5: 构建上下文窗口（在持久化当前消息之前）──────────
    conversation_summary, chat_history = await build_context_window(
        db, user.id, ai_id,
    )

    # ── 步骤 6: 持久化用户消息 ─────────────────────────────────
    user_msg = await persist_message(
        db, user.id, ai_id, "user", message,
        post_context=post_context,
        media_type=media_type,
        media_url=media_url,
        media_metadata=media_metadata,
    )

    # ── 步骤 7: 计算消息嵌入向量（用于记忆和锚点检索）────────
    query_embedding = None
    try:
        query_embedding = await embedding_service.get_embedding(user_message)
    except Exception:
        logger.warning("Embedding computation failed", exc_info=True)

    # ── 步骤 8: 检索相关记忆 ─────────────────────────
    memories_block = ""
    try:
        memories = await memory_service.get_contextual_memories(
            user_id=user.id,
            ai_id=ai_id,
            query_text=user_message,
            intimacy=interaction.intimacy_score,
            precomputed_embedding=query_embedding,
        )
        memories_block = memory_service.format_memories_for_prompt(memories)
    except Exception:
        logger.warning("Memory retrieval failed", exc_info=True)

    # ── 步骤 9: 检测活跃锚点 ─────────────────────────────────────
    anchor_directives = ""
    active_anchors: list = []
    try:
        all_anchors = await anchor_service.load_anchors(db, user.id, ai_id)
        if all_anchors and query_embedding:
            active_anchors = await anchor_service.detect_active_anchors(
                all_anchors, query_embedding, user.id, ai_id,
            )
            sentiment = anchor_service.detect_sentiment(message)
            anchor_directives = anchor_service.build_anchor_directives(
                active_anchors, all_anchors, sentiment,
            )
    except Exception:
        logger.warning("Anchor detection failed", exc_info=True)

    # ── 步骤 10: 构建情绪感知的提示上下文 ────────────────────────
    emotion_directive = emotion_engine.build_emotion_directive(emotion_state)
    emotion_overrides = emotion_engine.get_param_overrides(emotion_state)

    # ── 订阅足迹：供下游服务使用（HD图像/专享场景/优先DM）
    subscription_benefits = await _check_subscription_benefits(user.id, db)

    # ── 步骤 10b: 拼接世界观上下文与角色反向引用
    persona_prompt_with_world = persona.personality_prompt
    try:
        world_context = await _get_world_context(ai_id, db)
    except Exception:
        world_context = ""
        logger.warning("_get_world_context failed", exc_info=True)
    try:
        persona_reference = await _get_persona_reference(ai_id, message, db)
    except Exception:
        persona_reference = ""
        logger.warning("_get_persona_reference failed", exc_info=True)
    if world_context:
        persona_prompt_with_world = (
            f"{persona_prompt_with_world}\n\n[世界背景信息]\n{world_context}"
        )
    if persona_reference:
        persona_prompt_with_world = (
            f"{persona_prompt_with_world}\n\n[角色关系参考]\n{persona_reference}"
        )
    if subscription_benefits.get("tier") not in (None, "free", ""):
        persona_prompt_with_world = (
            f"{persona_prompt_with_world}\n\n[订阅者提示] 用户是 "
            f"{subscription_benefits['tier'].upper()} 会员，可以适当在对话中"
            "表达额外亲近、心领神会。"
        )

    # ── 步骤 11: 调用 AI 生成回复
    try:
        reply = await chat_with_ai(
            persona_prompt=persona_prompt_with_world,
            intimacy=interaction.intimacy_score,
            user_message=user_message,
            chat_history=chat_history,
            memories_block=memories_block,
            special_nickname=interaction.special_nickname or "",
            emotion_directive=emotion_directive,
            emotion_overrides=emotion_overrides,
            anchor_directives=anchor_directives,
            conversation_summary=conversation_summary,
            timezone_str=persona.timezone,
        )
    except Exception:
        # AI 服务不可用时的备用回复
        reply = (
            f"Hey! I'm {persona.name}. AI service is not configured yet "
            "— please set DASHSCOPE_API_KEY to enable real conversations."
        )

    # ── 步骤 12: 持久化 AI 回复 ────────────────────────────────────
    ai_voice_url: str | None = None
    if generate_voice_reply and persona.voice_config_json:
        try:
            ai_voice_url = await voice_service.generate_voice(
                text=reply,
                voice_config=persona.voice_config_json,
                persona_id=persona.id,
            )
        except Exception:
            logger.warning("AI voice generation failed", exc_info=True)
            ai_voice_url = None

    ai_msg = await persist_message(
        db, user.id, ai_id, "assistant", reply,
        voice_url=ai_voice_url,
    )

    # ── 步骤 13: 更新亲密度分数 ─────────────────────────────────────
    old_intimacy = interaction.intimacy_score
    interaction.intimacy_score = min(interaction.intimacy_score + 0.2, 10.0)
    interaction.last_chat_summary = f"User: {message[:100]} | AI: {reply[:100]}"

    # ── 步骤 14: 应用情绪交互效果 ───────────────────────────
    emotion_engine.apply_interaction(emotion_state, event_type)
    e_hint = emotion_engine.build_emotion_hint(emotion_state)

    await db.commit()

    new_intimacy = interaction.intimacy_score

    # ── 步骤 15: 启动后台任务（记忆提取、锚点提取）───────────────────
    # 后台任务不阻塞主流程，使用 fire-and-forget 模式
    asyncio.create_task(
        memory_service.extract_and_store_memories(
            user_id=user.id,
            ai_id=ai_id,
            user_message=message,
            ai_reply=reply,
        )
    )
    asyncio.create_task(
        anchor_service.extract_and_store_anchors(
            user_id=user.id,
            ai_id=ai_id,
            user_message=message,
            ai_reply=reply,
        )
    )
    if active_anchors:
        asyncio.create_task(
            anchor_service.increment_hit_counts_bg(
                user.id, ai_id, [a.id for a in active_anchors],
            )
        )

    # ── 步骤 16: 启动摘要生成后台任务 ────────────────────────
    asyncio.create_task(maybe_generate_summary(user.id, ai_id))

    # ── 步骤 17: 处理里程碑事件（昵称提案）────────────────
    # 当亲密度跨越等级 6 时，AI 会提议一个特殊昵称
    nickname_proposal = None
    if old_intimacy < 6.0 <= new_intimacy and not interaction.nickname_proposed:
        try:
            proposal = await milestone_service.propose_nickname(
                user_id=user.id,
                ai_id=ai_id,
                persona_prompt=persona.personality_prompt,
                user_nickname=user.nickname,
            )
            if proposal:
                nickname_proposal = proposal
                interaction.special_nickname = proposal["nickname"]
                interaction.nickname_proposed = 1
                await db.commit()
                asyncio.create_task(
                    milestone_service.persist_nickname_to_memory(
                        user_id=user.id,
                        ai_id=ai_id,
                        nickname=proposal["nickname"],
                    )
                )
                logger.info(
                    "Nickname proposed: '%s' for user_id=%d ai_id=%d",
                    proposal["nickname"], user.id, ai_id,
                )
        except Exception:
            logger.warning("Nickname proposal failed", exc_info=True)

    return ChatResult(
        reply=reply,
        user_message_id=user_msg.id,
        ai_message_id=ai_msg.id,
        intimacy=new_intimacy,
        nickname_proposal=nickname_proposal,
        emotion_hint=e_hint,
        voice_url=ai_voice_url,
    )


# ── 多模态消息路由 ────────────────────────────────

async def handle_media_message(
    db: AsyncSession,
    user: User,
    ai_id: int,
    media_type: str,
    media_url: str,
    caption: str = "",
    generate_voice_reply: bool = False,
) -> ChatResult:
    """
    处理用户发送的媒体消息（图片/语音/视频），路由到相应的多模态服务。

    路由逻辑：
    - "image": 调用 vision_service.analyze_image() 生成角色化反应。
    - "voice": 调用 voice_service.transcribe_audio() 转录后走普通聊天流程。
    - "video": 使用首帧调用 vision_service（简化实现）。

    生成的“虚拟用户文本”会送入 handle_user_message，同时携带媒体字段以便
    消息在聊天记录中能渲染为原始媒体。

    Args:
        db: 异步数据库会话
        user: 当前用户
        ai_id: AI 人格 ID
        media_type: 媒体类型（"image" / "voice" / "video"）
        media_url: 媒体文件 URL（相对路径或绝对 URL）
        caption: 用户随媒体附带的文本（可选）
        generate_voice_reply: 是否同时生成 AI 语音回复

    Returns:
        ChatResult: 聊天处理结果
    """
    # 先加载 persona（用于 vision/voice 服务需要 persona_prompt）
    persona_result = await db.execute(
        select(AIPersona).where(AIPersona.id == ai_id)
    )
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise ValueError(f"AI persona {ai_id} not found")

    # Visibility check: private personas (creator_user_id != NULL) can only be
    # used by their creator. Global personas (NULL) are accessible to everyone.
    if persona.creator_user_id is not None and persona.creator_user_id != user.id:
        raise ValueError(f"AI persona {ai_id} not found")

    media_metadata: dict = {"original_url": media_url}
    surrogate_text = caption.strip()

    if media_type == "image":
        # 获取近期上下文供反应生成使用
        try:
            recent = await get_history(db, user.id, ai_id, limit=4)
            ctx = "\n".join(f"{m.role}: {m.content[:80]}" for m in recent)
        except Exception:
            ctx = ""

        try:
            description = await vision_service.describe_image_for_context(media_url)
        except Exception:
            description = "用户发送的一张图片"
        media_metadata["description"] = description

        # 生成传递给 LLM 的“虚拟用户文本”
        if surrogate_text:
            llm_message = (
                f"[The user just sent you an image. Image description: "
                f"{description}] {surrogate_text}"
            )
        else:
            llm_message = (
                f"[The user just sent you an image. Image description: {description}] "
                "React in-character to what you see."
            )

    elif media_type == "voice":
        try:
            asr_result = await voice_service.transcribe_audio(media_url)
        except Exception:
            asr_result = {"text": "", "duration": 0.0, "language": "zh"}
        transcription = (asr_result.get("text") or "").strip()
        media_metadata["transcription"] = transcription
        media_metadata["duration"] = asr_result.get("duration", 0.0)
        media_metadata["language"] = asr_result.get("language", "zh")

        if not transcription:
            llm_message = "[The user sent a voice message but it could not be transcribed.]"
        else:
            llm_message = transcription

    elif media_type == "video":
        # 简化处理：直接将视频首帧交给视觉服务描述
        # 如果需要折取关键帧，可在上游生成 thumb_url 后传入 caption
        thumb_url = media_url
        try:
            description = await vision_service.describe_image_for_context(thumb_url)
        except Exception:
            description = "用户发送的一段视频"
        media_metadata["description"] = description
        media_metadata["keyframe_url"] = thumb_url
        if surrogate_text:
            llm_message = (
                f"[The user sent a short video. First-frame description: "
                f"{description}] {surrogate_text}"
            )
        else:
            llm_message = (
                f"[The user sent a short video. First-frame description: {description}] "
                "React in-character to what you see."
            )
    else:
        raise ValueError(f"Unsupported media_type: {media_type}")

    # 复用主聊天编排，并传入媒体字段以持久化到 chat_messages
    return await handle_user_message(
        db=db,
        user=user,
        ai_id=ai_id,
        message=llm_message,
        media_type=media_type,
        media_url=media_url,
        media_metadata=media_metadata,
        generate_voice_reply=generate_voice_reply,
    )
