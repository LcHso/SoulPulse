import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from core.security import get_current_user
from models.user import User
from models.ai_persona import AIPersona
from models.interaction import Interaction
from services.aliyun_ai_service import chat_with_ai
from services import memory_service, milestone_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    ai_id: int
    message: str
    post_context: str | None = None  # optional context from a post


class ChatResponse(BaseModel):
    reply: str
    intimacy: float
    nickname_proposal: dict | None = None  # {"nickname": "...", "message": "..."} when triggered


@router.post("/send", response_model=ChatResponse)
async def send_message(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a chat message to an AI persona, returns AI reply."""
    # Get persona
    persona_result = await db.execute(select(AIPersona).where(AIPersona.id == body.ai_id))
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="AI persona not found")

    # Get or create interaction
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id == body.ai_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    if not interaction:
        interaction = Interaction(user_id=current_user.id, ai_id=body.ai_id, intimacy_score=0.0)
        db.add(interaction)
        await db.commit()
        await db.refresh(interaction)

    # Build message, optionally including post context
    user_message = body.message
    if body.post_context:
        user_message = f"[Regarding this post: {body.post_context}]\n{body.message}"

    # Retrieve contextual memories (graceful degradation)
    memories_block = ""
    try:
        memories = await memory_service.get_contextual_memories(
            user_id=current_user.id,
            ai_id=body.ai_id,
            query_text=user_message,
            intimacy=interaction.intimacy_score,
        )
        memories_block = memory_service.format_memories_for_prompt(memories)
    except Exception:
        logger.warning("Memory retrieval failed, proceeding without memories", exc_info=True)

    # Call AI
    try:
        reply = await chat_with_ai(
            persona_prompt=persona.personality_prompt,
            intimacy=interaction.intimacy_score,
            user_message=user_message,
            memories_block=memories_block,
            special_nickname=interaction.special_nickname or "",
        )
    except Exception:
        # Fallback when AI service is not configured
        reply = f"Hey! I'm {persona.name}. AI service is not configured yet - please set DASHSCOPE_API_KEY in core/config.py to enable real conversations."

    # Capture pre-update intimacy for threshold detection
    old_intimacy = interaction.intimacy_score

    # Update intimacy slightly for chatting
    interaction.intimacy_score = min(interaction.intimacy_score + 0.2, 10.0)
    interaction.last_chat_summary = f"User: {body.message[:100]} | AI: {reply[:100]}"
    await db.commit()

    new_intimacy = interaction.intimacy_score

    # Fire-and-forget: extract and store memories from this conversation turn
    asyncio.create_task(
        memory_service.extract_and_store_memories(
            user_id=current_user.id,
            ai_id=body.ai_id,
            user_message=body.message,
            ai_reply=reply,
        )
    )

    # ── Milestone: nickname proposal at Lv 6 crossing ──────────
    nickname_proposal = None
    if old_intimacy < 6.0 <= new_intimacy and not interaction.nickname_proposed:
        try:
            proposal = await milestone_service.propose_nickname(
                user_id=current_user.id,
                ai_id=body.ai_id,
                persona_prompt=persona.personality_prompt,
                user_nickname=current_user.nickname,
            )
            if proposal:
                nickname_proposal = proposal
                # Save nickname and mark as proposed
                interaction.special_nickname = proposal["nickname"]
                interaction.nickname_proposed = 1
                await db.commit()
                # Persist to long-term memory (fire-and-forget)
                asyncio.create_task(
                    milestone_service.persist_nickname_to_memory(
                        user_id=current_user.id,
                        ai_id=body.ai_id,
                        nickname=proposal["nickname"],
                    )
                )
                logger.info(
                    "Nickname proposed: '%s' for user_id=%d ai_id=%d",
                    proposal["nickname"], current_user.id, body.ai_id,
                )
        except Exception:
            logger.warning("Nickname proposal failed", exc_info=True)

    return ChatResponse(
        reply=reply,
        intimacy=interaction.intimacy_score,
        nickname_proposal=nickname_proposal,
    )
