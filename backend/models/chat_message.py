"""Chat message: a single message in a user-AI conversation.

Every user message and AI reply is persisted here for history,
multi-turn context, and proactive DM delivery tracking.
"""

from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chatmsg_user_ai_id", "user_id", "ai_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    role: Mapped[str] = mapped_column(String(20), nullable=False)          # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)             # message text
    message_type: Mapped[str] = mapped_column(String(30), default="chat")  # "chat" / "proactive_dm" / "system"
    event: Mapped[str | None] = mapped_column(String(500), nullable=True)  # proactive DM event label
    post_context: Mapped[str | None] = mapped_column(String(500), nullable=True)

    delivered: Mapped[int] = mapped_column(Integer, default=1)             # 0 = unsent proactive DM
    summary_group: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_summaries.id"), nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
