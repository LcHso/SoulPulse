"""Chat service: message persistence, history, context window, and summary generation.

Core orchestration layer for the chat system. All chat flows (REST POST,
WebSocket receive) delegate to handle_user_message() for consistent behavior.
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
from services.aliyun_ai_service import chat_with_ai, _get_client
from services import (
    anchor_service,
    embedding_service,
    emotion_engine,
    memory_service,
    milestone_service,
)

logger = logging.getLogger(__name__)

# Summary generation: trigger after this many unsummarized messages
_SUMMARY_THRESHOLD = 10

# Number of recent raw messages passed to LLM as chat_history
_CONTEXT_RECENT_COUNT = 5


# ── Result type ─────────────────────────────────────────────────

@dataclass
class ChatResult:
    """Return value from handle_user_message."""

    reply: str
    user_message_id: int
    ai_message_id: int
    intimacy: float
    nickname_proposal: dict | None = field(default=None)
    emotion_hint: dict | None = field(default=None)


# ── Message persistence ─────────────────────────────────────────

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
    """Persist a single chat message and return it with its assigned id."""
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
    await db.flush()  # assigns id without committing the transaction
    return msg


# ── History retrieval ───────────────────────────────────────────

async def get_history(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
    limit: int = 30,
    before_id: int | None = None,
) -> list[ChatMessage]:
    """Return messages for a user-AI pair, oldest first.

    Cursor-paginated: if before_id is given, only return messages with
    id < before_id.  Results are in ascending id order (oldest first).
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
    messages.reverse()  # oldest first for display
    return messages


# ── Undelivered proactive DMs ───────────────────────────────────

async def get_undelivered_dms(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
) -> list[ChatMessage]:
    """Return proactive DMs not yet delivered, oldest first."""
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
    """Mark given message IDs as delivered."""
    if not message_ids:
        return
    stmt = select(ChatMessage).where(ChatMessage.id.in_(message_ids))
    result = await db.execute(stmt)
    for msg in result.scalars():
        msg.delivered = 1
    await db.flush()


# ── Context window construction ─────────────────────────────────

async def build_context_window(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
) -> tuple[str, list[dict]]:
    """Build the context window for LLM consumption.

    Returns:
        (conversation_summary, recent_messages)
        - conversation_summary: latest rolling summary text, or ""
        - recent_messages: last N messages as [{"role": ..., "content": ...}]

    NOTE: Call this BEFORE persisting the current user message so the
    window contains only prior conversation history.
    """
    # Latest summary
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

    # Last N messages (prior to the current turn)
    recent_stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id, ChatMessage.ai_id == ai_id)
        .order_by(ChatMessage.id.desc())
        .limit(_CONTEXT_RECENT_COUNT)
    )
    recent_result = await db.execute(recent_stmt)
    recent_msgs = list(recent_result.scalars().all())
    recent_msgs.reverse()  # oldest first

    recent_dicts = [
        {"role": m.role, "content": m.content}
        for m in recent_msgs
    ]

    return summary_text, recent_dicts


# ── Summary generation (fire-and-forget) ────────────────────────

_SUMMARY_SYSTEM_PROMPT = """\
You are a conversation summarizer. Given a previous summary (if any) and \
recent conversation turns, produce an updated summary that captures key facts, \
emotional developments, and ongoing topics. Be concise — under 200 words. \
Write in third person. Return ONLY the summary text, nothing else.\
"""


async def maybe_generate_summary(user_id: int, ai_id: int) -> None:
    """Generate a rolling summary if enough unsummarized messages exist.

    Runs as a fire-and-forget background task with its own DB session.
    Triggers when there are _SUMMARY_THRESHOLD+ unsummarized messages.
    """
    try:
        async with async_session() as db:
            # Find latest summary
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

            # Count unsummarized messages
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
                return  # not enough messages yet

            # Fetch unsummarized messages
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

            # Build conversation text for the LLM
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

            # Call LLM
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

            # Persist summary
            new_summary = ChatSummary(
                user_id=user_id,
                ai_id=ai_id,
                content=summary_content,
                message_range_start=messages[0].id,
                message_range_end=messages[-1].id,
            )
            db.add(new_summary)
            await db.flush()  # assigns new_summary.id

            # Tag messages with their summary group
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


# ── Main chat orchestration ─────────────────────────────────────

async def handle_user_message(
    db: AsyncSession,
    user: User,
    ai_id: int,
    message: str,
    post_context: str | None = None,
) -> ChatResult:
    """Process a user chat message end-to-end.

    Shared by both the REST POST endpoint and the WebSocket receive path.
    Handles: persona lookup, interaction upsert, emotion, embedding,
    memories, anchors, context window, LLM call, intimacy update,
    message persistence, and fire-and-forget background tasks.
    """
    # ── 1. Persona ──────────────────────────────────────────────
    persona_result = await db.execute(
        select(AIPersona).where(AIPersona.id == ai_id)
    )
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise ValueError(f"AI persona {ai_id} not found")

    # ── 2. Interaction (get or create) ──────────────────────────
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == user.id,
            Interaction.ai_id == ai_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    if not interaction:
        interaction = Interaction(user_id=user.id, ai_id=ai_id, intimacy_score=0.0)
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)

    # ── 3. Emotion state ────────────────────────────────────────
    emotion_state = await emotion_engine.get_or_create(db, user.id, ai_id)
    event_type = emotion_engine.classify_chat_event(message)

    # ── 4. Build user message with optional post context ────────
    user_message = message
    if post_context:
        user_message = f"[Regarding this post: {post_context}]\n{message}"

    # ── 5. Context window (BEFORE persisting current message) ───
    conversation_summary, chat_history = await build_context_window(
        db, user.id, ai_id,
    )

    # ── 6. Persist user message ─────────────────────────────────
    user_msg = await persist_message(
        db, user.id, ai_id, "user", message,
        post_context=post_context,
    )

    # ── 7. Compute embedding (reused for memories + anchors) ────
    query_embedding = None
    try:
        query_embedding = await embedding_service.get_embedding(user_message)
    except Exception:
        logger.warning("Embedding computation failed", exc_info=True)

    # ── 8. Retrieve contextual memories ─────────────────────────
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

    # ── 9. Anchor detection ─────────────────────────────────────
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

    # ── 10. Emotion-aware prompt context ────────────────────────
    emotion_directive = emotion_engine.build_emotion_directive(emotion_state)
    emotion_overrides = emotion_engine.get_param_overrides(emotion_state)

    # ── 11. Call AI ─────────────────────────────────────────────
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
        )
    except Exception:
        reply = (
            f"Hey! I'm {persona.name}. AI service is not configured yet "
            "— please set DASHSCOPE_API_KEY to enable real conversations."
        )

    # ── 12. Persist AI reply ────────────────────────────────────
    ai_msg = await persist_message(db, user.id, ai_id, "assistant", reply)

    # ── 13. Update intimacy ─────────────────────────────────────
    old_intimacy = interaction.intimacy_score
    interaction.intimacy_score = min(interaction.intimacy_score + 0.2, 10.0)
    interaction.last_chat_summary = f"User: {message[:100]} | AI: {reply[:100]}"

    # ── 14. Apply emotion interaction ───────────────────────────
    emotion_engine.apply_interaction(emotion_state, event_type)
    e_hint = emotion_engine.build_emotion_hint(emotion_state)

    await db.commit()

    new_intimacy = interaction.intimacy_score

    # ── 15. Fire-and-forget background tasks ────────────────────
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

    # ── 16. Summary generation (fire-and-forget) ────────────────
    asyncio.create_task(maybe_generate_summary(user.id, ai_id))

    # ── 17. Milestone: nickname proposal at Lv 6 crossing ───────
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
