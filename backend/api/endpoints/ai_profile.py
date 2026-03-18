from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import pytz

from core.database import get_db
from core.security import get_current_user
from models.user import User
from models.post import Post
from models.ai_persona import AIPersona
from models.interaction import Interaction

router = APIRouter(prefix="/api/ai", tags=["ai"])


class PostBrief(BaseModel):
    id: int
    media_url: str
    caption: str
    like_count: int
    is_locked: bool
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
    posts: list[PostBrief]


def _generate_status_label(timezone: str, profession: str) -> str:
    """Generate a realistic status label based on AI's timezone and current time."""
    try:
        tz = pytz.timezone(timezone)
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


@router.get("/profile/{ai_id}", response_model=AIProfileOut)
async def get_ai_profile(
    ai_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get AI persona profile with status and all posts."""
    result = await db.execute(select(AIPersona).where(AIPersona.id == ai_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="AI persona not found")

    # Fetch all posts for this AI, newest first
    posts_result = await db.execute(
        select(Post)
        .where(Post.ai_id == ai_id)
        .order_by(Post.created_at.desc())
    )
    posts = posts_result.scalars().all()

    # Look up user's intimacy with this AI for content permission
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id == ai_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    intimacy = interaction.intimacy_score if interaction else 0.0

    status_label = _generate_status_label(persona.timezone, persona.profession)

    # Build posts with lock state for close-friend content
    post_briefs = []
    for p in posts:
        locked = p.is_close_friend and intimacy < 6.0
        post_briefs.append(PostBrief(
            id=p.id,
            media_url="" if locked else p.media_url,
            caption="" if locked else p.caption,
            like_count=p.like_count,
            is_locked=locked,
            created_at=p.created_at.isoformat(),
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
        posts=post_briefs,
    )
