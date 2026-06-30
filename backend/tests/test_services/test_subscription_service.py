"""Unit tests for services.subscription_service.SubscriptionService.

Covers:
- check_benefit on the free tier (no active subscription)
- check_benefit on a premium tier (active subscription with benefits_json)
- subscribe creating a UserSubscription row + charging gems
- check_expirations deactivating subscriptions whose expires_at has passed
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Importing these modules registers their tables on Base.metadata so the
# session-scoped engine fixture creates them when ``create_all`` runs.
import models.subscription  # noqa: F401  (registers tables)
import models.gem_transaction  # noqa: F401  (registers tables)

from core.security import hash_password
from models.subscription import SubscriptionTier, UserSubscription
from models.user import User
from services.subscription_service import SubscriptionService


async def _make_user(
    db: AsyncSession, email: str = "sub_user@example.com", gems: int = 1000,
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("TestPass123!"),
        nickname="SubUser",
        gem_balance=gems,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_tier(
    db: AsyncSession,
    *,
    tier_name: str = "vip",
    display_name: str = "VIP月卡",
    price_gems: int = 100,
    duration_days: int = 30,
    benefits: dict | None = None,
) -> SubscriptionTier:
    tier = SubscriptionTier(
        tier_name=tier_name,
        display_name=display_name,
        price_gems=price_gems,
        duration_days=duration_days,
        benefits_json=benefits or {},
        is_active=True,
        sort_order=1,
    )
    db.add(tier)
    await db.commit()
    await db.refresh(tier)
    return tier


# ──────────────────────────────────────────────────────────────────────
# check_benefit / get_user_tier
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_feature_access_free_tier(db: AsyncSession):
    """A user with no active subscription is on the free tier and gets no
    premium benefits."""
    svc = SubscriptionService()
    user = await _make_user(db, email="sub_free@example.com")

    assert await svc.get_user_tier(db, user.id) == "free"
    assert await svc.check_benefit(db, user.id, "hd_images") is False
    assert await svc.check_benefit(db, user.id, "priority_dm") is False

    status = await svc.get_subscription_status(db, user.id)
    assert status["tier"] == "free"
    assert status["active"] is False
    assert status["benefits"] == {}


@pytest.mark.asyncio
async def test_check_feature_access_premium(db: AsyncSession):
    """A user with an active premium subscription unlocks the benefits flagged
    on their tier's benefits_json."""
    svc = SubscriptionService()
    user = await _make_user(db, email="sub_premium@example.com")
    tier = await _make_tier(db, benefits={
        "hd_images": True,
        "priority_dm": True,
        "exclusive_scenes": False,
    })

    now = datetime.utcnow()
    db.add(UserSubscription(
        user_id=user.id,
        tier_id=tier.id,
        started_at=now,
        expires_at=now + timedelta(days=30),
        is_active=True,
        auto_renew=False,
    ))
    await db.commit()

    assert await svc.get_user_tier(db, user.id) == "vip"
    assert await svc.check_benefit(db, user.id, "hd_images") is True
    assert await svc.check_benefit(db, user.id, "priority_dm") is True
    assert await svc.check_benefit(db, user.id, "exclusive_scenes") is False


# ──────────────────────────────────────────────────────────────────────
# subscribe (apply_subscription)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_apply_subscription_creates_record(db: AsyncSession):
    """Subscribing creates a UserSubscription row with the right tier_id and
    expiry, and deducts the price in gems from the user's balance."""
    svc = SubscriptionService()
    user = await _make_user(db, email="sub_apply@example.com", gems=500)
    tier = await _make_tier(
        db,
        tier_name="svip",
        display_name="SVIP季卡",
        price_gems=200,
        duration_days=90,
        benefits={"daily_gems": 20, "hd_images": True},
    )

    result = await svc.subscribe(db, user_id=user.id, tier_id=tier.id)

    assert result["tier"] == "svip"
    assert result["gems_charged"] == 200
    assert result["remaining_balance"] == 300

    rows = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    subs = list(rows.scalars().all())
    assert len(subs) == 1
    assert subs[0].tier_id == tier.id
    assert subs[0].is_active is True
    assert subs[0].expires_at > datetime.utcnow()
    # Approximately 90 days out (allow generous slack for clock drift).
    delta = subs[0].expires_at - subs[0].started_at
    assert 89 <= delta.days <= 91


# ──────────────────────────────────────────────────────────────────────
# check_expirations
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subscription_expiry_logic(db: AsyncSession):
    """check_expirations flips is_active=False on subscriptions whose
    expires_at is in the past, and leaves still-valid ones alone."""
    svc = SubscriptionService()
    user = await _make_user(db, email="sub_expiry@example.com")
    tier = await _make_tier(db, tier_name="vip_exp")

    now = datetime.utcnow()
    expired = UserSubscription(
        user_id=user.id, tier_id=tier.id,
        started_at=now - timedelta(days=40),
        expires_at=now - timedelta(days=5),
        is_active=True, auto_renew=False,
    )
    still_valid = UserSubscription(
        user_id=user.id, tier_id=tier.id,
        started_at=now - timedelta(days=10),
        expires_at=now + timedelta(days=20),
        is_active=True, auto_renew=False,
    )
    db.add_all([expired, still_valid])
    await db.commit()
    await db.refresh(expired)
    await db.refresh(still_valid)

    count = await svc.check_expirations(db)
    assert count == 1

    await db.refresh(expired)
    await db.refresh(still_valid)
    assert expired.is_active is False
    assert still_valid.is_active is True
