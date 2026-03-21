"""Notification API endpoints."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from typing import Optional

from core.database import get_db
from core.security import get_current_user
from core.utils import to_utc_iso
from models.user import User
from models.notification import Notification

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    type: str
    title: str
    body: str
    data_json: Optional[str] = None
    is_read: bool
    created_at: str


class NotificationListOut(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int
    has_more: bool


@router.get("", response_model=NotificationListOut)
async def get_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get user notifications, newest first."""
    result = await db.execute(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    )
    notifications = result.scalars().all()
    has_more = len(notifications) > limit
    if has_more:
        notifications = notifications[:limit]

    unread_result = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == current_user.id, Notification.is_read == 0)
    )
    unread_count = unread_result.scalar() or 0

    return NotificationListOut(
        notifications=[
            NotificationOut(
                id=n.id,
                type=n.type,
                title=n.title,
                body=n.body,
                data_json=n.data_json,
                is_read=bool(n.is_read),
                created_at=to_utc_iso(n.created_at),
            )
            for n in notifications
        ],
        unread_count=unread_count,
        has_more=has_more,
    )


@router.get("/unread-count")
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get count of unread notifications."""
    result = await db.execute(
        select(func.count(Notification.id))
        .where(Notification.user_id == current_user.id, Notification.is_read == 0)
    )
    return {"unread_count": result.scalar() or 0}


@router.post("/mark-read")
async def mark_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark all notifications as read."""
    await db.execute(
        update(Notification)
        .where(Notification.user_id == current_user.id, Notification.is_read == 0)
        .values(is_read=1)
    )
    await db.commit()
    return {"message": "All notifications marked as read"}


@router.post("/{notification_id}/read")
async def mark_one_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif:
        notif.is_read = 1
        await db.commit()
    return {"message": "ok"}
