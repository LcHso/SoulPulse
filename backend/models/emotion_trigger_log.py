"""Cooldown / audit log for emotion-driven proactive triggers."""

from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class EmotionTriggerLog(Base):
    __tablename__ = "emotion_trigger_logs"
    __table_args__ = (
        Index("ix_trigger_user_ai_type", "user_id", "ai_id", "trigger_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
