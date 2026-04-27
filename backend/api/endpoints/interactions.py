"""
User-AI Interactions Endpoint Module

Provides endpoints for retrieving user-AI relationship summaries,
including intimacy levels, special nicknames, and last chat timestamps.

Endpoints:
    GET /api/interactions/summary - Get all user-AI relationship summaries
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from core.database import get_db
from core.security import get_current_user
from core.utils import to_utc_iso
from models.user import User
from models.ai_persona import AIPersona
from models.interaction import Interaction
from models.chat_message import ChatMessage

router = APIRouter(prefix="/api/interactions", tags=["interactions"])


# ── Response Models ──────────────────────────────────────────────

class InteractionSummaryOut(BaseModel):
    """
    Interaction summary response model.

    Attributes:
        ai_id: AI persona ID
        ai_name: AI persona name
        avatar_url: AI persona avatar URL
        intimacy_score: Intimacy score (0-10)
        intimacy_level: Relationship level label
        special_nickname: User's special nickname for the AI (if any)
        last_chat_at: Timestamp of last message in the conversation
    """
    ai_id: int
    ai_name: str
    avatar_url: str
    intimacy_score: float
    intimacy_level: str
    special_nickname: str | None
    last_chat_at: str


# ── Helper Functions ──────────────────────────────────────────────

def _map_intimacy_level(score: float) -> str:
    """
    Map intimacy score (0-10) to relationship level.

    Args:
        score: Intimacy score (0-10)

    Returns:
        str: Relationship level label
    """
    if score < 2.0:
        return "stranger"
    elif score < 4.0:
        return "acquaintance"
    elif score < 6.0:
        return "friend"
    elif score < 8.0:
        return "close_friend"
    else:
        return "soulmate"


# ── Endpoints ──────────────────────────────────────────────────────

@router.get("/summary", response_model=list[InteractionSummaryOut])
async def get_interactions_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the authenticated user's relationship summary with all AIs.

    Returns a list of all user-AI interactions, including intimacy scores,
    relationship levels, special nicknames, and last chat timestamps.
    Results are ordered by intimacy score (highest first).

    Args:
        db: Async database session
        current_user: Current authenticated user

    Returns:
        list[InteractionSummaryOut]: List of interaction summaries
    """
    # Query all interactions for the current user
    interactions_result = await db.execute(
        select(Interaction).where(Interaction.user_id == current_user.id)
    )
    interactions = interactions_result.scalars().all()

    if not interactions:
        return []

    # Get AI persona IDs from interactions
    ai_ids = [i.ai_id for i in interactions]

    # Load AI personas
    personas_result = await db.execute(
        select(AIPersona).where(AIPersona.id.in_(ai_ids))
    )
    persona_map = {p.id: p for p in personas_result.scalars().all()}

    # Get last chat timestamp for each AI
    # Subquery to find the max created_at for each user-ai pair
    last_chat_result = await db.execute(
        select(
            ChatMessage.ai_id,
            func.max(ChatMessage.created_at).label("last_chat_at")
        )
        .where(
            ChatMessage.user_id == current_user.id,
            ChatMessage.ai_id.in_(ai_ids)
        )
        .group_by(ChatMessage.ai_id)
    )
    last_chat_map = {row.ai_id: row.last_chat_at for row in last_chat_result.all()}

    # Build response
    summaries = []
    for interaction in interactions:
        persona = persona_map.get(interaction.ai_id)
        if not persona:
            continue

        last_chat_at = last_chat_map.get(interaction.ai_id)

        summaries.append(InteractionSummaryOut(
            ai_id=interaction.ai_id,
            ai_name=persona.name,
            avatar_url=persona.avatar_url or "",
            intimacy_score=interaction.intimacy_score,
            intimacy_level=_map_intimacy_level(interaction.intimacy_score),
            special_nickname=interaction.special_nickname,
            last_chat_at=to_utc_iso(last_chat_at),
        ))

    # Sort by intimacy score (highest first)
    summaries.sort(key=lambda s: s.intimacy_score, reverse=True)
    return summaries
