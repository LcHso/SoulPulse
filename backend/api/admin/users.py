"""M5: User & Trust Safety endpoints"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user, _to_utc_iso

router = APIRouter(tags=["admin-users"])


class UserOut(BaseModel):
    id: int
    email: str
    nickname: str
    avatar_url: str | None
    gem_balance: int
    is_admin: int
    created_at: str


class UserDetail(BaseModel):
    id: int
    email: str
    nickname: str
    avatar_url: str | None
    gender: str
    gem_balance: int
    is_admin: int
    created_at: str
    total_messages: int
    persona_interactions: list[dict]


class ModerationLogOut(BaseModel):
    id: int
    content_type: str
    content_id: int
    user_id: int
    ai_id: int
    reason: str
    action_taken: str
    reviewer_id: int
    created_at: str


class ModerationCreate(BaseModel):
    content_type: str
    content_id: int = 0
    user_id: int = 0
    ai_id: int = 0
    reason: str = ""
    action_taken: str = ""


# ── User listing (migrated) ──

@router.get("/users")
async def list_users(
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.user import User

    query = select(User).order_by(User.created_at.desc())
    count_q = select(func.count()).select_from(User)

    if search:
        query = query.where(User.email.contains(search) | User.nickname.contains(search))
        count_q = count_q.where(User.email.contains(search) | User.nickname.contains(search))

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    users = result.scalars().all()

    return {
        "users": [
            UserOut(
                id=u.id, email=u.email, nickname=u.nickname,
                avatar_url=u.avatar_url, gem_balance=u.gem_balance,
                is_admin=u.is_admin, created_at=_to_utc_iso(u.created_at),
            )
            for u in users
        ],
        "total": total,
        "has_more": offset + limit < total,
    }


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.user import User
    from models.chat_message import ChatMessage

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Total messages
    msg_r = await db.execute(
        select(func.count(ChatMessage.id)).where(ChatMessage.user_id == user_id)
    )
    total_messages = msg_r.scalar() or 0

    # Per-persona breakdown
    persona_r = await db.execute(
        select(
            ChatMessage.ai_id,
            func.count(ChatMessage.id).label("count"),
        )
        .where(ChatMessage.user_id == user_id)
        .group_by(ChatMessage.ai_id)
    )
    interactions = [{"ai_id": ai_id, "message_count": cnt} for ai_id, cnt in persona_r.all()]

    return UserDetail(
        id=user.id, email=user.email, nickname=user.nickname,
        avatar_url=user.avatar_url, gender=user.gender,
        gem_balance=user.gem_balance, is_admin=user.is_admin,
        created_at=_to_utc_iso(user.created_at),
        total_messages=total_messages,
        persona_interactions=interactions,
    )


@router.post("/users/{user_id}/set-admin")
async def set_user_admin(
    user_id: int,
    is_admin: int = 1,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.user import User
    from core.config import settings
    
    # Only super admin (id=1 or configured super_admin_id) can modify admin roles
    super_admin_id = getattr(settings, 'SUPER_ADMIN_ID', 1)
    if admin.id != 1 and admin.id != super_admin_id:
        raise HTTPException(status_code=403, detail="Only super admin can modify admin roles")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_admin = is_admin
    await db.commit()
    return {"message": "Admin role updated", "user_id": user_id, "is_admin": is_admin}


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: int,
    reason: str = "",
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.user import User
    from models.content_moderation_log import ContentModerationLog

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Mark as banned (we use is_admin = -1 to indicate banned since we can't add columns to production)
    # Actually, let's store it in moderation logs and check gem_balance or create a moderation entry
    db.add(ContentModerationLog(
        content_type="user_ban",
        user_id=user_id,
        reason=reason,
        action_taken="ban",
        reviewer_id=admin.id,
    ))
    await db.commit()
    return {"message": "User banned", "user_id": user_id}


@router.post("/users/{user_id}/unban")
async def unban_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.content_moderation_log import ContentModerationLog

    db.add(ContentModerationLog(
        content_type="user_unban",
        user_id=user_id,
        reason="",
        action_taken="unban",
        reviewer_id=admin.id,
    ))
    await db.commit()
    return {"message": "User unbanned", "user_id": user_id}


# ── Chat audit ──

@router.get("/users/{user_id}/chat-history")
async def get_chat_history(
    user_id: int,
    ai_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.chat_message import ChatMessage

    query = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
    )
    if ai_id:
        query = query.where(ChatMessage.ai_id == ai_id)

    result = await db.execute(query.offset(offset).limit(limit))
    msgs = result.scalars().all()
    return [
        {
            "id": m.id,
            "user_id": m.user_id,
            "ai_id": m.ai_id,
            "role": m.role,
            "content": m.content,
            "created_at": _to_utc_iso(m.created_at),
        }
        for m in msgs
    ]


# ── Moderation logs ──

@router.get("/moderation-logs")
async def list_moderation_logs(
    limit: int = 50,
    offset: int = 0,
    content_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.content_moderation_log import ContentModerationLog

    query = select(ContentModerationLog).order_by(ContentModerationLog.created_at.desc())
    if content_type:
        query = query.where(ContentModerationLog.content_type == content_type)

    result = await db.execute(query.offset(offset).limit(limit))
    logs = result.scalars().all()
    return [
        ModerationLogOut(
            id=l.id, content_type=l.content_type, content_id=l.content_id,
            user_id=l.user_id, ai_id=l.ai_id, reason=l.reason,
            action_taken=l.action_taken, reviewer_id=l.reviewer_id,
            created_at=_to_utc_iso(l.created_at),
        )
        for l in logs
    ]


@router.post("/moderation-logs")
async def create_moderation_log(
    req: ModerationCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.content_moderation_log import ContentModerationLog

    entry = ContentModerationLog(
        content_type=req.content_type, content_id=req.content_id,
        user_id=req.user_id, ai_id=req.ai_id, reason=req.reason,
        action_taken=req.action_taken, reviewer_id=admin.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return ModerationLogOut(
        id=entry.id, content_type=entry.content_type, content_id=entry.content_id,
        user_id=entry.user_id, ai_id=entry.ai_id, reason=entry.reason,
        action_taken=entry.action_taken, reviewer_id=entry.reviewer_id,
        created_at=_to_utc_iso(entry.created_at),
    )
