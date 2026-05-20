"""User-facing subscription endpoints.

Surface tier catalog, current subscription status, subscribe/cancel
operations, plus event-campaign listing and progress/claim handling.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models.event_campaign import EventCampaign, UserEventProgress
from models.gem_transaction import GemTransaction
from models.subscription import SubscriptionTier
from models.user import User
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/subscription", tags=["subscription"])


# ── Schemas ────────────────────────────────────────────────────────


class TierOut(BaseModel):
    id: int
    tier_name: str
    display_name: str
    price_gems: int
    duration_days: int
    benefits: dict
    sort_order: int


class SubscriptionStatusOut(BaseModel):
    tier: str
    active: bool
    tier_id: Optional[int] = None
    tier_display_name: Optional[str] = None
    started_at: Optional[str] = None
    expires_at: Optional[str] = None
    auto_renew: bool = False
    benefits: dict = {}


class CampaignOut(BaseModel):
    id: int
    event_name: str
    description: Optional[str]
    event_type: str
    start_date: str
    end_date: str
    reward_pool: dict
    progress_tracker_type: str
    max_progress: int
    participation_condition: Optional[str] = None


class CampaignProgressOut(BaseModel):
    event_id: int
    progress: int
    max_progress: int
    is_completed: bool
    rewards_claimed: bool
    started_at: Optional[str]
    completed_at: Optional[str]


# ── Tier endpoints ─────────────────────────────────────────────────


@router.get("/tiers", response_model=list[TierOut])
async def list_tiers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all active subscription tiers ordered by sort_order."""
    result = await db.execute(
        select(SubscriptionTier)
        .where(SubscriptionTier.is_active.is_(True))
        .order_by(SubscriptionTier.sort_order, SubscriptionTier.id)
    )
    return [
        TierOut(
            id=t.id,
            tier_name=t.tier_name,
            display_name=t.display_name,
            price_gems=t.price_gems,
            duration_days=t.duration_days,
            benefits=t.benefits_json or {},
            sort_order=t.sort_order,
        )
        for t in result.scalars().all()
    ]


@router.get("/my-subscription", response_model=SubscriptionStatusOut)
async def get_my_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the authenticated user's current subscription status."""
    svc = SubscriptionService()
    status = await svc.get_subscription_status(db, current_user.id)
    return SubscriptionStatusOut(**status)


@router.post("/subscribe/{tier_id}")
async def subscribe(
    tier_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Subscribe to (or renew/upgrade) the given tier."""
    svc = SubscriptionService()
    try:
        return await svc.subscribe(db, current_user.id, tier_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/cancel")
async def cancel_subscription(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disable auto-renewal on the active subscription."""
    svc = SubscriptionService()
    return await svc.cancel_auto_renew(db, current_user.id)


# ── Event campaign endpoints ───────────────────────────────────────


@router.get("/events", response_model=list[CampaignOut])
async def list_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List active event campaigns currently in their date window."""
    now = datetime.utcnow()
    result = await db.execute(
        select(EventCampaign)
        .where(
            EventCampaign.is_active.is_(True),
            EventCampaign.start_date <= now,
            EventCampaign.end_date >= now,
        )
        .order_by(EventCampaign.end_date.asc())
    )
    return [
        CampaignOut(
            id=e.id,
            event_name=e.event_name,
            description=e.description,
            event_type=e.event_type,
            start_date=e.start_date.isoformat(),
            end_date=e.end_date.isoformat(),
            reward_pool=e.reward_pool_json or {},
            progress_tracker_type=e.progress_tracker_type,
            max_progress=e.max_progress,
            participation_condition=e.participation_condition,
        )
        for e in result.scalars().all()
    ]


async def _get_or_create_progress(
    db: AsyncSession, user_id: int, event_id: int
) -> UserEventProgress:
    result = await db.execute(
        select(UserEventProgress).where(
            UserEventProgress.user_id == user_id,
            UserEventProgress.event_id == event_id,
        )
    )
    progress = result.scalar_one_or_none()
    if progress:
        return progress
    progress = UserEventProgress(
        user_id=user_id, event_id=event_id, progress=0,
    )
    db.add(progress)
    await db.flush()
    return progress


@router.get("/events/{event_id}/progress", response_model=CampaignProgressOut)
async def get_event_progress(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the user's progress in the given campaign."""
    event_res = await db.execute(
        select(EventCampaign).where(EventCampaign.id == event_id)
    )
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    progress = await _get_or_create_progress(db, current_user.id, event_id)
    await db.commit()
    return CampaignProgressOut(
        event_id=event_id,
        progress=progress.progress,
        max_progress=event.max_progress,
        is_completed=bool(progress.is_completed),
        rewards_claimed=bool(progress.rewards_claimed),
        started_at=progress.started_at.isoformat() if progress.started_at else None,
        completed_at=progress.completed_at.isoformat() if progress.completed_at else None,
    )


@router.post("/events/{event_id}/claim")
async def claim_event_rewards(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Claim the campaign's reward pool once the user has completed it."""
    event_res = await db.execute(
        select(EventCampaign).where(EventCampaign.id == event_id)
    )
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    progress = await _get_or_create_progress(db, current_user.id, event_id)

    # Auto-mark complete if user reached the max progress.
    if not progress.is_completed and progress.progress >= event.max_progress:
        progress.is_completed = True
        progress.completed_at = datetime.utcnow()

    if not progress.is_completed:
        raise HTTPException(status_code=400, detail="Event not completed yet")
    if progress.rewards_claimed:
        raise HTTPException(status_code=400, detail="Rewards already claimed")

    rewards = event.reward_pool_json or {}
    bonus_gems = int(rewards.get("bonus_gems") or 0)
    if bonus_gems > 0:
        current_user.gem_balance += bonus_gems
        db.add(GemTransaction(
            user_id=current_user.id,
            amount=bonus_gems,
            balance_after=current_user.gem_balance,
            tx_type="event_reward",
            reference_id=str(event_id),
            description=f"Event reward: {event.event_name}",
        ))

    progress.rewards_claimed = True
    await db.commit()

    return {
        "event_id": event_id,
        "rewards_claimed": True,
        "bonus_gems": bonus_gems,
        "rewards": rewards,
        "remaining_balance": current_user.gem_balance,
    }
