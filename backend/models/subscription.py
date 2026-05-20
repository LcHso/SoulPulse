"""Subscription/pass system for tiered monetization.

Defines the subscription tier catalog and per-user active subscriptions.
Used by SubscriptionService to gate VIP/SVIP features (HD images, priority
DMs, exclusive scenes, daily gem rewards, unlimited replay, etc.).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class SubscriptionTier(Base):
    """Catalog of available subscription tiers (free / vip / svip / ...)."""

    __tablename__ = "subscription_tiers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Internal name e.g. "free", "vip", "svip"
    tier_name: Mapped[str] = mapped_column(String(50))
    # Display name shown to user e.g. "VIP月卡", "SVIP年卡"
    display_name: Mapped[str] = mapped_column(String(100))
    # Gem cost for one subscription period (0 for free tier)
    price_gems: Mapped[int] = mapped_column(Integer, default=0)
    # How long a single purchase lasts (days)
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    # Benefit flags: {"daily_gems": 10, "hd_images": true, "priority_dm": true,
    #                 "exclusive_scenes": true, "unlimited_replay": true}
    benefits_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class UserSubscription(Base):
    """A specific user's active or historical subscription."""

    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    tier_id: Mapped[int] = mapped_column(Integer, ForeignKey("subscription_tiers.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    # Tracks last day daily-gem reward was credited (avoid double-grant)
    last_daily_reward_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True
    )
