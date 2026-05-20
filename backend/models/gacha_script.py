from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class GachaScript(Base):
    __tablename__ = "gacha_scripts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    persona_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False, index=True)
    storyline_json: Mapped[str] = mapped_column(Text, default="[]")
    system_prompt_override: Mapped[str] = mapped_column(Text, default="")
    gem_cost: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── Monetization depth (Plan Task 4) ─────────────────────────
    # Preview CG image used in the storefront to entice purchase.
    preview_cg_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Bonus reward when the user finishes every branch of the storyline.
    # Example: {"bonus_gems": 50, "exclusive_cg_id": 12, "outfit_id": 4}
    completion_reward_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Difficulty rating from 1 (easy) to 5 (hardest).
    difficulty_rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Free-form duration label e.g. "15-20 minutes".
    estimated_duration: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Whether the storyline branches into multiple endings.
    has_multiple_endings: Mapped[bool] = mapped_column(Boolean, default=False)
