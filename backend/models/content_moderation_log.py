from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class ContentModerationLog(Base):
    __tablename__ = "content_moderation_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    content_id: Mapped[int] = mapped_column(Integer, default=0)
    user_id: Mapped[int] = mapped_column(Integer, default=0, index=True)
    ai_id: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text, default="")
    action_taken: Mapped[str] = mapped_column(String(50), default="")
    reviewer_id: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
