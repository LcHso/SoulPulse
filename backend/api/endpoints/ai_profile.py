from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import pytz

from core.database import get_db
from core.security import get_current_user, get_current_user_optional
from core.utils import to_utc_iso
from models.user import User
from models.post import Post
from models.ai_persona import AIPersona
from models.interaction import Interaction
from models.follow import Follow
from models.user_like import UserLike
from models.saved_post import SavedPost
from models.emotion_state import EmotionState
from services import emotion_engine

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ── Schemas ─────────────────────────────────────────────────────

class AIPersonaBrief(BaseModel):
    id: int
    name: str
    bio: str
    profession: str
    avatar_url: str
    gender_tag: str
    category: str
    archetype: str


class AIPersonaListOut(BaseModel):
    personas: list[AIPersonaBrief]
    total: int


class PostBrief(BaseModel):
    id: int
    media_url: str
    caption: str
    like_count: int
    is_locked: bool
    is_liked: bool = False
    is_saved: bool = False
    ai_id: int = 0
    ai_name: str = ""
    ai_avatar: str = ""
    created_at: str


class AIProfileOut(BaseModel):
    id: int
    name: str
    bio: str
    profession: str
    avatar_url: str
    gender_tag: str
    ins_style_tags: str
    timezone: str
    status_label: str
    post_count: int
    follower_count: int
    is_following: bool
    intimacy_score: float
    intimacy_level: str
    posts: list[PostBrief]


class InteractionSummary(BaseModel):
    ai_id: int
    ai_name: str
    ai_avatar: str
    intimacy_score: float
    intimacy_level: str
    emotion_hint: dict


class EmotionOut(BaseModel):
    energy_level: str
    mood: str
    longing: bool
    energy: float
    pleasure: float
    persona_local_time: str = ""
    persona_timezone: str = ""


# ── Helpers ─────────────────────────────────────────────────────

def _intimacy_level(score: float) -> str:
    if score < 2.0:
        return "Stranger"
    elif score < 4.0:
        return "Acquaintance"
    elif score < 6.0:
        return "Friend"
    elif score < 8.0:
        return "Close Friend"
    else:
        return "Soulmate"


def _generate_status_label(tz_name: str, profession: str) -> str:
    try:
        tz = pytz.timezone(tz_name)
        local_hour = datetime.now(tz).hour
    except Exception:
        local_hour = datetime.utcnow().hour

    if 0 <= local_hour < 6:
        return "Sleeping"
    elif 6 <= local_hour < 8:
        return "Just woke up"
    elif 8 <= local_hour < 10:
        return "Coffee time"
    elif 10 <= local_hour < 12:
        if "photo" in profession.lower():
            return "Out shooting photos"
        return "Working"
    elif 12 <= local_hour < 14:
        return "Lunch break"
    elif 14 <= local_hour < 17:
        if "photo" in profession.lower():
            return "Editing photos"
        return "Busy working"
    elif 17 <= local_hour < 19:
        return "Evening walk"
    elif 19 <= local_hour < 21:
        return "Dinner & chill"
    elif 21 <= local_hour < 23:
        return "Winding down"
    else:
        return "About to sleep"


# ── Persona listing ─────────────────────────────────────────────

@router.get("/personas", response_model=AIPersonaListOut)
async def list_personas(
    category: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Search by name, bio, or archetype"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """List all active AI personas, optionally filtered by category or search query.
    
    This endpoint is public and does not require authentication.
    """
    query = select(AIPersona).where(AIPersona.is_active == 1)
    if category:
        query = query.where(AIPersona.category == category)
    if q:
        search_term = f"%{q}%"
        query = query.where(
            (AIPersona.name.ilike(search_term)) |
            (AIPersona.bio.ilike(search_term)) |
            (AIPersona.archetype.ilike(search_term)) |
            (AIPersona.profession.ilike(search_term))
        )
    query = query.order_by(AIPersona.sort_order, AIPersona.id)

    result = await db.execute(query)
    personas = result.scalars().all()

    return AIPersonaListOut(
        personas=[
            AIPersonaBrief(
                id=p.id, name=p.name, bio=p.bio, profession=p.profession,
                avatar_url=p.avatar_url, gender_tag=p.gender_tag,
                category=p.category, archetype=p.archetype,
            )
            for p in personas
        ],
        total=len(personas),
    )


# ── Profile with intimacy + follow ──────────────────────────────

@router.get("/profile/{ai_id}", response_model=AIProfileOut)
async def get_ai_profile(
    ai_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get AI persona profile with intimacy, follow status, and posts."""
    result = await db.execute(select(AIPersona).where(AIPersona.id == ai_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="AI persona not found")

    posts_result = await db.execute(
        select(Post).where(Post.ai_id == ai_id).order_by(Post.created_at.desc())
    )
    posts = posts_result.scalars().all()

    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id == ai_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    intimacy = interaction.intimacy_score if interaction else 0.0

    # Follower count
    follower_result = await db.execute(
        select(func.count(Follow.id)).where(Follow.ai_id == ai_id)
    )
    follower_count = follower_result.scalar() or 0

    # Is following
    follow_result = await db.execute(
        select(Follow).where(
            Follow.user_id == current_user.id,
            Follow.ai_id == ai_id,
        )
    )
    is_following = follow_result.scalar_one_or_none() is not None

    status_label = _generate_status_label(persona.timezone, persona.profession)

    # Fetch user's liked and saved post IDs for this persona's posts
    post_ids = [p.id for p in posts]
    liked_ids = set()
    saved_ids = set()
    if post_ids:
        liked_result = await db.execute(
            select(UserLike.post_id).where(
                UserLike.user_id == current_user.id,
                UserLike.post_id.in_(post_ids),
            )
        )
        liked_ids = {row[0] for row in liked_result.all()}

        saved_result = await db.execute(
            select(SavedPost.post_id).where(
                SavedPost.user_id == current_user.id,
                SavedPost.post_id.in_(post_ids),
            )
        )
        saved_ids = {row[0] for row in saved_result.all()}

    post_briefs = []
    for p in posts:
        locked = p.is_close_friend and intimacy < 6.0
        post_briefs.append(PostBrief(
            id=p.id,
            media_url="" if locked else p.media_url,
            caption="" if locked else p.caption,
            like_count=p.like_count,
            is_locked=locked,
            is_liked=p.id in liked_ids,
            is_saved=p.id in saved_ids,
            ai_id=persona.id,
            ai_name=persona.name,
            ai_avatar=persona.avatar_url,
            created_at=to_utc_iso(p.created_at),
        ))

    return AIProfileOut(
        id=persona.id,
        name=persona.name,
        bio=persona.bio,
        profession=persona.profession,
        avatar_url=persona.avatar_url,
        gender_tag=persona.gender_tag,
        ins_style_tags=persona.ins_style_tags,
        timezone=persona.timezone,
        status_label=status_label,
        post_count=len(posts),
        follower_count=follower_count,
        is_following=is_following,
        intimacy_score=intimacy,
        intimacy_level=_intimacy_level(intimacy),
        posts=post_briefs,
    )


# ── Follow / Unfollow ──────────────────────────────────────────

@router.post("/{ai_id}/follow")
async def follow_ai(
    ai_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Follow an AI persona."""
    existing = await db.execute(
        select(Follow).where(
            Follow.user_id == current_user.id,
            Follow.ai_id == ai_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"following": True}

    db.add(Follow(user_id=current_user.id, ai_id=ai_id))
    await db.commit()
    return {"following": True}


@router.delete("/{ai_id}/follow")
async def unfollow_ai(
    ai_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unfollow an AI persona."""
    existing = await db.execute(
        select(Follow).where(
            Follow.user_id == current_user.id,
            Follow.ai_id == ai_id,
        )
    )
    follow = existing.scalar_one_or_none()
    if follow:
        await db.delete(follow)
        await db.commit()
    return {"following": False}


# ── Emotion status ──────────────────────────────────────────────

@router.get("/emotion/{ai_id}", response_model=EmotionOut)
async def get_emotion_status(
    ai_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get AI emotion status for the user-AI relationship."""
    emo = await emotion_engine.get_or_create(db, current_user.id, ai_id)
    hint = emotion_engine.build_emotion_hint(emo)

    # Compute persona local time for timezone indicator
    persona_local_time = ""
    persona_timezone = ""
    persona_result = await db.execute(
        select(AIPersona).where(AIPersona.id == ai_id)
    )
    persona = persona_result.scalar_one_or_none()
    if persona:
        persona_timezone = persona.timezone or "Asia/Shanghai"
        try:
            tz = pytz.timezone(persona_timezone)
            persona_local_time = datetime.now(tz).strftime("%H:%M")
        except Exception:
            persona_local_time = datetime.utcnow().strftime("%H:%M")

    return EmotionOut(
        energy_level=hint["energy_level"],
        mood=hint["mood"],
        longing=hint["longing"],
        energy=emo.energy,
        pleasure=emo.pleasure,
        persona_local_time=persona_local_time,
        persona_timezone=persona_timezone,
    )


# ── Interactions summary ────────────────────────────────────────

@router.get("/interactions/summary", response_model=list[InteractionSummary])
async def get_interactions_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get summary of all user-AI interactions with intimacy and emotion."""
    interactions_result = await db.execute(
        select(Interaction).where(Interaction.user_id == current_user.id)
    )
    interactions = interactions_result.scalars().all()

    if not interactions:
        return []

    ai_ids = [i.ai_id for i in interactions]
    personas_result = await db.execute(
        select(AIPersona).where(AIPersona.id.in_(ai_ids))
    )
    persona_map = {p.id: p for p in personas_result.scalars().all()}

    summaries = []
    for interaction in interactions:
        persona = persona_map.get(interaction.ai_id)
        if not persona:
            continue

        emo = await emotion_engine.get_or_create(db, current_user.id, interaction.ai_id)
        hint = emotion_engine.build_emotion_hint(emo)

        summaries.append(InteractionSummary(
            ai_id=interaction.ai_id,
            ai_name=persona.name,
            ai_avatar=persona.avatar_url,
            intimacy_score=interaction.intimacy_score,
            intimacy_level=_intimacy_level(interaction.intimacy_score),
            emotion_hint=hint,
        ))

    summaries.sort(key=lambda s: s.intimacy_score, reverse=True)
    return summaries
