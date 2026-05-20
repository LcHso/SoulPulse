"""Limited-time event campaigns for urgency-driven monetization.

Models the catalog of running campaigns (七夕限定 / 圣诞活动 / etc.) and
the per-user progress / reward-claim state. Drives task lists, gacha
rate-up banners, and exclusive scenes.
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
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class EventCampaign(Base):
    """A time-bound campaign players can join for limited rewards."""

    __tablename__ = "event_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    event_name: Mapped[str] = mapped_column(String(200))  # e.g. "七夕限定约会"
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # collection / daily_task / gacha_rate_up / limited_scene
    event_type: Mapped[str] = mapped_column(String(50))
    start_date: Mapped[datetime] = mapped_column(DateTime)
    end_date: Mapped[datetime] = mapped_column(DateTime)
    # {"completion_cg_id": 5, "bonus_gems": 100, "exclusive_outfit_id": 3}
    reward_pool_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    participation_condition: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    # counter / checklist / score
    progress_tracker_type: Mapped[str] = mapped_column(String(50), default="counter")
    max_progress: Mapped[int] = mapped_column(Integer, default=7)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class UserEventProgress(Base):
    """Tracks how far a user has advanced in a given campaign."""

    __tablename__ = "user_event_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("event_campaigns.id"), index=True
    )
    progress: Mapped[int] = mapped_column(Integer, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    rewards_claimed: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
