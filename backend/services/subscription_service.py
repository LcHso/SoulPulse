"""Subscription management service.

Centralizes business logic for tier lookup, benefit checks, purchase /
upgrade, daily-reward processing, and expiration sweeps. Used by chat,
content gating, and the emotion scheduler.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.gem_transaction import GemTransaction
from models.subscription import SubscriptionTier, UserSubscription
from models.user import User

logger = logging.getLogger(__name__)


class SubscriptionService:
    """Stateless helper around subscription_tiers + user_subscriptions."""

    DEFAULT_TIER = "free"

    # ── Read helpers ────────────────────────────────────────────────

    async def _get_active_subscription(
        self, db: AsyncSession, user_id: int
    ) -> Optional[UserSubscription]:
        """Return the user's currently active, non-expired subscription, if any."""
        now = datetime.utcnow()
        result = await db.execute(
            select(UserSubscription)
            .where(
                UserSubscription.user_id == user_id,
                UserSubscription.is_active.is_(True),
                UserSubscription.expires_at > now,
            )
            .order_by(UserSubscription.expires_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_tier(
        self, db: AsyncSession, tier_id: int
    ) -> Optional[SubscriptionTier]:
        result = await db.execute(
            select(SubscriptionTier).where(SubscriptionTier.id == tier_id)
        )
        return result.scalar_one_or_none()

    async def get_user_tier(self, db: AsyncSession, user_id: int) -> str:
        """Return the user's current subscription tier name (defaults to ``free``)."""
        sub = await self._get_active_subscription(db, user_id)
        if not sub:
            return self.DEFAULT_TIER
        tier = await self._get_tier(db, sub.tier_id)
        return tier.tier_name if tier else self.DEFAULT_TIER

    async def check_benefit(
        self, db: AsyncSession, user_id: int, benefit_key: str
    ) -> bool:
        """Whether the user's active tier grants the named benefit."""
        sub = await self._get_active_subscription(db, user_id)
        if not sub:
            return False
        tier = await self._get_tier(db, sub.tier_id)
        if not tier or not tier.benefits_json:
            return False
        return bool(tier.benefits_json.get(benefit_key))

    async def get_subscription_status(
        self, db: AsyncSession, user_id: int
    ) -> dict:
        """Snapshot used by user-facing endpoints."""
        sub = await self._get_active_subscription(db, user_id)
        if not sub:
            return {
                "tier": self.DEFAULT_TIER,
                "active": False,
                "tier_id": None,
                "started_at": None,
                "expires_at": None,
                "auto_renew": False,
                "benefits": {},
            }
        tier = await self._get_tier(db, sub.tier_id)
        return {
            "tier": tier.tier_name if tier else self.DEFAULT_TIER,
            "tier_display_name": tier.display_name if tier else "",
            "active": True,
            "tier_id": sub.tier_id,
            "started_at": sub.started_at.isoformat() if sub.started_at else None,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
            "auto_renew": bool(sub.auto_renew),
            "benefits": (tier.benefits_json or {}) if tier else {},
        }

    # ── Mutations ───────────────────────────────────────────────────

    async def subscribe(
        self, db: AsyncSession, user_id: int, tier_id: int
    ) -> dict:
        """Create or upgrade a subscription, deducting gems from the user.

        If the user already has an active subscription:
          - same tier: extends ``expires_at`` by ``duration_days``.
          - different tier: deactivates the old one and starts a fresh one.
        """
        tier = await self._get_tier(db, tier_id)
        if not tier or not tier.is_active:
            raise ValueError("Subscription tier not found or inactive")

        user_res = await db.execute(select(User).where(User.id == user_id))
        user = user_res.scalar_one_or_none()
        if not user:
            raise ValueError("User not found")

        cost = int(tier.price_gems or 0)
        if cost > 0 and user.gem_balance < cost:
            raise ValueError("Insufficient gem balance")

        now = datetime.utcnow()
        existing = await self._get_active_subscription(db, user_id)

        if existing and existing.tier_id == tier_id:
            # Renew: extend expiry from current expiry (or now if expired earlier).
            base = max(existing.expires_at, now)
            existing.expires_at = base + timedelta(days=int(tier.duration_days or 30))
            sub = existing
        else:
            if existing:
                existing.is_active = False
            sub = UserSubscription(
                user_id=user_id,
                tier_id=tier_id,
                started_at=now,
                expires_at=now + timedelta(days=int(tier.duration_days or 30)),
                is_active=True,
                auto_renew=False,
            )
            db.add(sub)

        # Charge gems and log transaction.
        if cost > 0:
            user.gem_balance -= cost
            db.add(GemTransaction(
                user_id=user_id,
                amount=-cost,
                balance_after=user.gem_balance,
                tx_type="subscription",
                reference_id=str(tier_id),
                description=f"Subscribed to {tier.display_name}",
            ))

        await db.commit()
        await db.refresh(sub)

        return {
            "subscription_id": sub.id,
            "tier": tier.tier_name,
            "tier_display_name": tier.display_name,
            "expires_at": sub.expires_at.isoformat(),
            "gems_charged": cost,
            "remaining_balance": user.gem_balance,
        }

    async def cancel_auto_renew(
        self, db: AsyncSession, user_id: int
    ) -> dict:
        """Disable auto-renewal but keep current subscription until expiry."""
        sub = await self._get_active_subscription(db, user_id)
        if not sub:
            return {"cancelled": False, "reason": "no_active_subscription"}
        sub.auto_renew = False
        await db.commit()
        return {
            "cancelled": True,
            "expires_at": sub.expires_at.isoformat() if sub.expires_at else None,
        }

    # ── Scheduler hooks ─────────────────────────────────────────────

    async def process_daily_rewards(self, db: AsyncSession) -> int:
        """Grant daily gem rewards to all active subscribers.

        Idempotent per UTC day via ``last_daily_reward_at``.
        Returns the number of users credited.
        """
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)

        active_res = await db.execute(
            select(UserSubscription).where(
                UserSubscription.is_active.is_(True),
                UserSubscription.expires_at > now,
            )
        )
        subs = active_res.scalars().all()
        if not subs:
            return 0

        tier_ids = list({s.tier_id for s in subs})
        tier_res = await db.execute(
            select(SubscriptionTier).where(SubscriptionTier.id.in_(tier_ids))
        )
        tiers = {t.id: t for t in tier_res.scalars().all()}

        granted = 0
        for sub in subs:
            tier = tiers.get(sub.tier_id)
            if not tier or not tier.benefits_json:
                continue
            daily = int(tier.benefits_json.get("daily_gems") or 0)
            if daily <= 0:
                continue
            if sub.last_daily_reward_at and sub.last_daily_reward_at >= today_start:
                continue  # already granted today

            user_res = await db.execute(select(User).where(User.id == sub.user_id))
            user = user_res.scalar_one_or_none()
            if not user:
                continue
            user.gem_balance += daily
            db.add(GemTransaction(
                user_id=sub.user_id,
                amount=daily,
                balance_after=user.gem_balance,
                tx_type="subscription_daily",
                reference_id=str(sub.id),
                description=f"Daily reward ({tier.display_name})",
            ))
            sub.last_daily_reward_at = now
            granted += 1

        await db.commit()
        if granted:
            logger.info("[subscription] daily rewards granted to %d users", granted)
        return granted

    async def check_expirations(self, db: AsyncSession) -> int:
        """Deactivate subscriptions whose ``expires_at`` has passed."""
        now = datetime.utcnow()
        result = await db.execute(
            select(UserSubscription).where(
                UserSubscription.is_active.is_(True),
                UserSubscription.expires_at <= now,
            )
        )
        expired = result.scalars().all()
        for sub in expired:
            sub.is_active = False
        if expired:
            await db.commit()
            logger.info("[subscription] %d subscriptions expired", len(expired))
        return len(expired)
