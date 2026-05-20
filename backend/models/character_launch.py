"""Character launch campaign and rotation system (Plan Task 9.3-9.4).

Models supporting the 4-phase character launch pipeline and the
character availability / rotation rules.

Pipeline phases:
- Phase 1 "teaser":     ~3 days before launch — silhouette posts,
                        cross-character hint posts, push notifications.
- Phase 2 "launched":   the launch day — reveal CG, welcome scene,
                        launch gacha at a discounted rate.
- Phase 3 "settling":   first ~2 weeks after launch — boosted post
                        frequency and a 7-day daily-chat event.
- Phase 4 "integrated": campaign archived; the persona enters the
                        normal content rotation.

Availability types control how a persona can be reached after launch:
permanent / seasonal / limited / archived (archive pass gated).
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


class CharacterLaunchCampaign(Base):
    """A scheduled launch campaign for a single AI persona.

    Table: character_launch_campaigns

    A campaign is created some time before the public launch date and
    drives content automation across four phases (see module docstring).
    Phase boundaries are computed from ``launch_date``:
    ``teaser_start = launch_date - 3d`` and
    ``settling_end  = launch_date + 14d`` by default.
    """

    __tablename__ = "character_launch_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    persona_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_personas.id"), index=True
    )
    campaign_name: Mapped[str] = mapped_column(String(200))

    # ── Phase scheduling ───────────────────────────────────────
    # 3 days before launch — phase 1 starts here.
    teaser_start: Mapped[datetime] = mapped_column(DateTime)
    # The public launch moment — phase 2.
    launch_date: Mapped[datetime] = mapped_column(DateTime)
    # 2 weeks after launch — phase 3 ends, transition to integrated.
    settling_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ── Phase 1: Teaser content ────────────────────────────────
    # Silhouette image used in the official teaser post.
    teaser_silhouette_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Day-by-day hint copy, e.g.:
    # [{"day": -3, "hint": "..."}, {"day": -2, "hint": "..."}]
    teaser_hints_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    # ── Phase 2: Launch day content ────────────────────────────
    # Full reveal CG posted on launch day.
    reveal_cg_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Optional welcome scene (FK to chat_scenes; not enforced to avoid
    # ordering issues in table creation).
    welcome_scene_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Optional launch gacha (FK to gacha_scripts; logical reference).
    launch_gacha_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Discount applied to the launch gacha (percentage off).
    launch_discount_percent: Mapped[int] = mapped_column(Integer, default=20)

    # ── Phase 3: Settling-in content ───────────────────────────
    # Extra posts per day during the settling window.
    daily_post_boost: Mapped[int] = mapped_column(Integer, default=3)
    # Settling-in event payload, e.g.:
    # {"type": "daily_chat", "days": 7, "reward": {"cg_id": X, "gems": 50}}
    launch_event_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # ── Status ────────────────────────────────────────────────
    # planned | teaser | launched | settling | integrated
    current_phase: Mapped[str] = mapped_column(String(20), default="planned")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class CharacterAvailability(Base):
    """Rotation / availability rules for a single persona.

    Table: character_availability

    A persona without a row here is treated as ``permanent`` and always
    available. Otherwise:
    - permanent: always available
    - seasonal:  available only inside [available_from, available_until]
    - limited:   available only inside [available_from, available_until]
    - archived:  only reachable when the user holds an archive pass
    """

    __tablename__ = "character_availability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    persona_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_personas.id"), unique=True, index=True
    )
    # permanent | seasonal | limited | archived
    availability_type: Mapped[str] = mapped_column(String(50), default="permanent")
    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    available_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # When True, an archive-pass entitlement is required to access the persona.
    archive_pass_required: Mapped[bool] = mapped_column(Boolean, default=False)
    # Higher values surface ahead of others when several are simultaneously available.
    rotation_priority: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
