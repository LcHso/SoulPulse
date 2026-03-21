"""Per-relationship emotion state: physiology (energy) + psychology (pleasure,
activation, longing, security).  One row per (user_id, ai_id) pair."""

from datetime import datetime

from sqlalchemy import Integer, Float, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class EmotionState(Base):
    __tablename__ = "emotion_states"
    __table_args__ = (
        Index("ix_emotion_user_ai", "user_id", "ai_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # Physiology
    energy: Mapped[float] = mapped_column(Float, default=80.0)

    # Psychology (multi-dimensional)
    pleasure: Mapped[float] = mapped_column(Float, default=0.3)       # -1.0 .. 1.0
    activation: Mapped[float] = mapped_column(Float, default=0.2)     # -1.0 .. 1.0
    longing: Mapped[float] = mapped_column(Float, default=0.0)        #  0.0 .. 1.0
    security: Mapped[float] = mapped_column(Float, default=0.5)       # -1.0 .. 1.0

    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
