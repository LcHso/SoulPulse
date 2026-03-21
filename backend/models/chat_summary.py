"""Chat summary: a rolling LLM-generated summary of conversation turns.

Generated every ~10 user messages. Each summary incorporates the previous
summary + last 10 turns, compressing context for the LLM without unbounded
token growth.
"""

from datetime import datetime

from sqlalchemy import Integer, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ChatSummary(Base):
    __tablename__ = "chat_summaries"
    __table_args__ = (
        Index("ix_chatsummary_user_ai_time", "user_id", "ai_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)  # summary text
    message_range_start: Mapped[int] = mapped_column(Integer, nullable=False)  # first chat_messages.id
    message_range_end: Mapped[int] = mapped_column(Integer, nullable=False)    # last chat_messages.id

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
