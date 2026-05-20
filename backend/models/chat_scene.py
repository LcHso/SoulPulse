"""Chat scene definitions for immersive narrative experiences.

Implements Plan Task 3:
- ChatScene: A reusable narrative scene template attached to a persona.
  Examples include "雨天咖啡馆", "深夜电话", "一起看星星".
- UserSceneProgress: Per-user progress tracking for a scene session.

Scenes overlay onto a persona's normal personality_prompt via
``system_prompt_addon`` while active, drive interactive choice arcs, and
auto-complete after a configurable number of messages.
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


class ChatScene(Base):
    """Reusable conversation scene attached to a persona.

    Table: chat_scenes

    A ChatScene is a curated narrative environment (date, comfort call,
    stargazing, etc.) which, when activated by a user, overlays additional
    instructions on top of the persona's base prompt. Scenes can be gated
    behind intimacy thresholds, gem cost, gacha, milestones, or events, and
    can grant rewards on completion (intimacy bonus, CG unlock, achievements).
    """

    __tablename__ = "chat_scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Persona this scene belongs to
    persona_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_personas.id"), index=True
    )

    # Display name shown in the scene picker
    scene_name: Mapped[str] = mapped_column(String(200))
    # Category: daily_life, date, adventure, emotional_support, spicy, activity
    scene_type: Mapped[str] = mapped_column(String(50))
    # Detailed environment description (used in prompt and UI)
    setting_description: Mapped[str] = mapped_column(Text)
    # Optional mood preset: intimate, warm, exciting, melancholic, playful
    mood_preset: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # Prompt fragment overlaid on personality_prompt while scene is active
    system_prompt_addon: Mapped[str] = mapped_column(Text)

    # ── Access gating ──────────────────────────────────────────
    # Minimum intimacy score required to access this scene
    required_intimacy: Mapped[int] = mapped_column(Integer, default=0)
    # Unlock model: free, gem, gacha, milestone, event
    unlock_type: Mapped[str] = mapped_column(String(50), default="free")
    # Gem cost when unlock_type == "gem"
    unlock_cost: Mapped[int] = mapped_column(Integer, default=0)

    # ── Lifecycle ──────────────────────────────────────────────
    # Scene auto-ends after this many messages
    max_messages: Mapped[int] = mapped_column(Integer, default=20)
    # Reward payload, e.g. {"intimacy_bonus": 5, "cg_unlock_id": 3, "achievement": "first_date"}
    completion_reward_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── Presentation ───────────────────────────────────────────
    # Background CG image displayed while scene is active
    scene_cg_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Soft-delete / visibility flag
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Manual ordering for the scene list
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class UserSceneProgress(Base):
    """Per-user runtime state for a scene session.

    Table: user_scene_progress

    A row is created when a user starts a scene; ``status`` tracks the
    lifecycle (in_progress -> completed/abandoned). The ``messages_count``
    is incremented as the user exchanges messages within the scene and is
    used to detect auto-completion. ``choices_made_json`` captures any
    interactive choice points triggered during the scene.
    """

    __tablename__ = "user_scene_progress"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), index=True)
    scene_id: Mapped[int] = mapped_column(Integer, ForeignKey("chat_scenes.id"), index=True)
    persona_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), index=True)

    # Lifecycle state: in_progress, completed, abandoned
    status: Mapped[str] = mapped_column(String(20), default="in_progress")

    # Number of messages exchanged inside this scene session
    messages_count: Mapped[int] = mapped_column(Integer, default=0)

    # List of choices made by user, e.g.
    # [{"key": "A", "text": "拥抱他", "at": "2026-05-19T..."}]
    choices_made_json: Mapped[Optional[list]] = mapped_column(JSON, default=list)

    started_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
