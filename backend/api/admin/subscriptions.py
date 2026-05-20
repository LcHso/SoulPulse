"""Admin endpoints for subscription tier and campaign management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import get_current_admin_user
from core.database import get_db
from models.event_campaign import EventCampaign, UserEventProgress
from models.gem_transaction import GemTransaction
from models.subscription import SubscriptionTier, UserSubscription

router = APIRouter(prefix="/subscriptions", tags=["admin-subscriptions"])


# ── Schemas ────────────────────────────────────────────────────────


class TierOut(BaseModel):
    id: int
    tier_name: str
    display_name: str
    price_gems: int
    duration_days: int
    benefits_json: dict
    is_active: bool
    sort_order: int


class TierCreate(BaseModel):
    tier_name: str = Field(..., max_length=50)
    display_name: str = Field(..., max_length=100)
    price_gems: int = 0
    duration_days: int = 30
    benefits_json: dict = Field(default_factory=dict)
    is_active: bool = True
    sort_order: int = 0


class TierUpdate(BaseModel):
    tier_name: Optional[str] = None
    display_name: Optional[str] = None
    price_gems: Optional[int] = None
    duration_days: Optional[int] = None
    benefits_json: Optional[dict] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CampaignOut(BaseModel):
    id: int
    event_name: str
    description: Optional[str]
    event_type: str
    start_date: str
    end_date: str
    reward_pool_json: dict
    participation_condition: Optional[str]
    progress_tracker_type: str
    max_progress: int
    is_active: bool


class CampaignCreate(BaseModel):
    event_name: str = Field(..., max_length=200)
    description: Optional[str] = None
    event_type: str = Field(..., max_length=50)
    start_date: datetime
    end_date: datetime
    reward_pool_json: dict = Field(default_factory=dict)
    participation_condition: Optional[str] = None
    progress_tracker_type: str = "counter"
    max_progress: int = 7
    is_active: bool = True


class CampaignUpdate(BaseModel):
    event_name: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    reward_pool_json: Optional[dict] = None
    participation_condition: Optional[str] = None
    progress_tracker_type: Optional[str] = None
    max_progress: Optional[int] = None
    is_active: Optional[bool] = None


# ── Mappers ────────────────────────────────────────────────────────


def _tier_to_out(t: SubscriptionTier) -> TierOut:
    return TierOut(
        id=t.id,
        tier_name=t.tier_name,
        display_name=t.display_name,
        price_gems=t.price_gems,
        duration_days=t.duration_days,
        benefits_json=t.benefits_json or {},
        is_active=bool(t.is_active),
        sort_order=t.sort_order,
    )


def _campaign_to_out(c: EventCampaign) -> CampaignOut:
    return CampaignOut(
        id=c.id,
        event_name=c.event_name,
        description=c.description,
        event_type=c.event_type,
        start_date=c.start_date.isoformat() if c.start_date else "",
        end_date=c.end_date.isoformat() if c.end_date else "",
        reward_pool_json=c.reward_pool_json or {},
        participation_condition=c.participation_condition,
        progress_tracker_type=c.progress_tracker_type,
        max_progress=c.max_progress,
        is_active=bool(c.is_active),
    )


# ── Tier endpoints ─────────────────────────────────────────────────


@router.get("/tiers")
async def list_tiers(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    query = select(SubscriptionTier).order_by(
        SubscriptionTier.sort_order, SubscriptionTier.id
    )
    if is_active is not None:
        query = query.where(SubscriptionTier.is_active.is_(is_active))
    result = await db.execute(query)
    return [_tier_to_out(t) for t in result.scalars().all()]


@router.post("/tiers")
async def create_tier(
    body: TierCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    tier = SubscriptionTier(**body.model_dump())
    db.add(tier)
    await db.commit()
    await db.refresh(tier)
    return _tier_to_out(tier)


@router.put("/tiers/{tier_id}")
async def update_tier(
    tier_id: int,
    body: TierUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    result = await db.execute(
        select(SubscriptionTier).where(SubscriptionTier.id == tier_id)
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(tier, field, value)
    await db.commit()
    await db.refresh(tier)
    return _tier_to_out(tier)


@router.delete("/tiers/{tier_id}")
async def delete_tier(
    tier_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    result = await db.execute(
        select(SubscriptionTier).where(SubscriptionTier.id == tier_id)
    )
    tier = result.scalar_one_or_none()
    if not tier:
        raise HTTPException(status_code=404, detail="Tier not found")
    tier.is_active = False
    await db.commit()
    return {"message": "Tier archived", "id": tier_id}


# ── Campaign endpoints ─────────────────────────────────────────────


@router.get("/campaigns")
async def list_campaigns(
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    query = select(EventCampaign).order_by(EventCampaign.end_date.desc())
    if is_active is not None:
        query = query.where(EventCampaign.is_active.is_(is_active))
    result = await db.execute(query)
    return [_campaign_to_out(c) for c in result.scalars().all()]


@router.post("/campaigns")
async def create_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    campaign = EventCampaign(**body.model_dump())
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return _campaign_to_out(campaign)


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    result = await db.execute(
        select(EventCampaign).where(EventCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(campaign, field, value)
    await db.commit()
    await db.refresh(campaign)
    return _campaign_to_out(campaign)


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    result = await db.execute(
        select(EventCampaign).where(EventCampaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.is_active = False
    await db.commit()
    return {"message": "Campaign archived", "id": campaign_id}


# ── Stats ──────────────────────────────────────────────────────────


@router.get("/stats")
async def subscription_stats(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Aggregate subscription metrics: active counts, revenue, conversion."""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=days)

    # Active subscribers (still within expiry window).
    active_total_r = await db.execute(
        select(func.count(UserSubscription.id)).where(
            UserSubscription.is_active.is_(True),
            UserSubscription.expires_at > now,
        )
    )
    active_total = active_total_r.scalar() or 0

    # Per-tier active breakdown.
    by_tier_r = await db.execute(
        select(
            UserSubscription.tier_id,
            func.count(UserSubscription.id),
        )
        .where(
            UserSubscription.is_active.is_(True),
            UserSubscription.expires_at > now,
        )
        .group_by(UserSubscription.tier_id)
    )
    tier_rows = by_tier_r.all()

    tier_id_list = [r[0] for r in tier_rows]
    tier_lookup = {}
    if tier_id_list:
        tlr = await db.execute(
            select(SubscriptionTier).where(SubscriptionTier.id.in_(tier_id_list))
        )
        tier_lookup = {t.id: t for t in tlr.scalars().all()}
    by_tier = [
        {
            "tier_id": tid,
            "tier_name": tier_lookup[tid].tier_name if tid in tier_lookup else "",
            "display_name": tier_lookup[tid].display_name if tid in tier_lookup else "",
            "active_subscribers": int(count or 0),
        }
        for tid, count in tier_rows
    ]

    # New subscriptions in window.
    new_subs_r = await db.execute(
        select(func.count(UserSubscription.id)).where(
            UserSubscription.started_at >= cutoff,
        )
    )
    new_subs = new_subs_r.scalar() or 0

    # Revenue (gems spent on subscriptions and daily rewards granted).
    revenue_r = await db.execute(
        select(func.sum(GemTransaction.amount))
        .where(
            GemTransaction.tx_type == "subscription",
            GemTransaction.created_at >= cutoff,
        )
    )
    revenue = abs(revenue_r.scalar() or 0)

    daily_payout_r = await db.execute(
        select(func.sum(GemTransaction.amount))
        .where(
            GemTransaction.tx_type == "subscription_daily",
            GemTransaction.created_at >= cutoff,
        )
    )
    daily_payout = daily_payout_r.scalar() or 0

    # Crude conversion rate: distinct subscribers / distinct gem-spending users.
    sub_users_r = await db.execute(
        select(func.count(func.distinct(UserSubscription.user_id))).where(
            UserSubscription.started_at >= cutoff,
        )
    )
    sub_users = sub_users_r.scalar() or 0

    spending_users_r = await db.execute(
        select(func.count(func.distinct(GemTransaction.user_id))).where(
            GemTransaction.amount < 0,
            GemTransaction.created_at >= cutoff,
        )
    )
    spending_users = spending_users_r.scalar() or 0
    conversion_rate = (
        round(sub_users / spending_users, 4) if spending_users else 0.0
    )

    return {
        "period_days": days,
        "active_subscribers": active_total,
        "new_subscriptions": new_subs,
        "subscription_revenue_gems": revenue,
        "daily_reward_payout_gems": daily_payout,
        "conversion_rate": conversion_rate,
        "by_tier": by_tier,
    }


@router.get("/campaigns/{campaign_id}/stats")
async def campaign_stats(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Per-campaign participation metrics."""
    event_res = await db.execute(
        select(EventCampaign).where(EventCampaign.id == campaign_id)
    )
    event = event_res.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Campaign not found")

    participants_r = await db.execute(
        select(func.count(UserEventProgress.id)).where(
            UserEventProgress.event_id == campaign_id
        )
    )
    completed_r = await db.execute(
        select(func.count(UserEventProgress.id)).where(
            UserEventProgress.event_id == campaign_id,
            UserEventProgress.is_completed.is_(True),
        )
    )
    claimed_r = await db.execute(
        select(func.count(UserEventProgress.id)).where(
            UserEventProgress.event_id == campaign_id,
            UserEventProgress.rewards_claimed.is_(True),
        )
    )

    return {
        "campaign_id": campaign_id,
        "event_name": event.event_name,
        "participants": participants_r.scalar() or 0,
        "completed": completed_r.scalar() or 0,
        "claimed": claimed_r.scalar() or 0,
    }
