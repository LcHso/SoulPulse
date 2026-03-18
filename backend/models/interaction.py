from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False, index=True)
    intimacy_score: Mapped[float] = mapped_column(Float, default=0.0)
    last_chat_summary: Mapped[str] = mapped_column(Text, default="")
    special_nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    nickname_proposed: Mapped[bool] = mapped_column(Integer, default=0)  # SQLite has no bool
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
