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
from dataclasses import dataclass, field

from sqlalchemy import select, func
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

async def handle_user_message(
    db: AsyncSession,
    user: User,
    ai_id: int,
    message: str,
    post_context: str | None = None,
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

    # ── 步骤 11: 调用 AI 生成回复 ─────────────────────────────────────────────
    try:
        reply = await chat_with_ai(
            persona_prompt=persona.personality_prompt,
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
    ai_msg = await persist_message(db, user.id, ai_id, "assistant", reply)

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
    )
