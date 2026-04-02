"""
Admin emotion service - Direct read/write of emotion_states table.
Does NOT touch emotion_engine.py.
"""

import logging
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("soulpulse.admin.emotion")


def _to_utc_iso(dt) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def get_emotion_states(db: AsyncSession, persona_id: int, limit: int = 50):
    from models.emotion_state import EmotionState

    result = await db.execute(
        select(EmotionState)
        .where(EmotionState.ai_id == persona_id)
        .order_by(EmotionState.updated_at.desc())
        .limit(limit)
    )
    states = result.scalars().all()
    return [
        {
            "id": s.id,
            "user_id": s.user_id,
            "ai_id": s.ai_id,
            "energy": s.energy,
            "pleasure": s.pleasure,
            "activation": s.activation,
            "longing": s.longing,
            "security": s.security,
            "updated_at": _to_utc_iso(s.updated_at),
        }
        for s in states
    ]


async def get_emotion_state(db: AsyncSession, user_id: int, persona_id: int):
    from models.emotion_state import EmotionState

    result = await db.execute(
        select(EmotionState)
        .where(EmotionState.user_id == user_id, EmotionState.ai_id == persona_id)
    )
    s = result.scalar_one_or_none()
    if not s:
        return None
    return {
        "id": s.id,
        "user_id": s.user_id,
        "ai_id": s.ai_id,
        "energy": s.energy,
        "pleasure": s.pleasure,
        "activation": s.activation,
        "longing": s.longing,
        "security": s.security,
        "updated_at": _to_utc_iso(s.updated_at),
    }


async def update_emotion_state(db: AsyncSession, user_id: int, persona_id: int, updates: dict):
    from models.emotion_state import EmotionState

    result = await db.execute(
        select(EmotionState)
        .where(EmotionState.user_id == user_id, EmotionState.ai_id == persona_id)
    )
    state = result.scalar_one_or_none()
    if not state:
        return None

    for field, value in updates.items():
        if hasattr(state, field):
            setattr(state, field, value)

    await db.commit()
    await db.refresh(state)

    return {
        "id": state.id,
        "user_id": state.user_id,
        "ai_id": state.ai_id,
        "energy": state.energy,
        "pleasure": state.pleasure,
        "activation": state.activation,
        "longing": state.longing,
        "security": state.security,
        "updated_at": _to_utc_iso(state.updated_at),
    }
