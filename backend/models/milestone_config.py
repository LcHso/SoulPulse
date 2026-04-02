from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class MilestoneConfig(Base):
    __tablename__ = "milestone_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    persona_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False, index=True)
    intimacy_level: Mapped[int] = mapped_column(Integer, nullable=False)
    level_name: Mapped[str] = mapped_column(String(100), default="")
    min_score: Mapped[int] = mapped_column(Integer, default=0)
    unlock_features_json: Mapped[str] = mapped_column(Text, default="[]")
    trigger_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
