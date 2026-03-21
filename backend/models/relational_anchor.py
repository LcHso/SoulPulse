"""Relational anchor: a learned emotional sensitivity for a user-AI pair.

Anchor types:
  - taboo      — topics the user dislikes or reacts negatively to
  - preference — things the user particularly likes or values
  - fear       — anxieties, insecurities, or worries
  - boundary   — explicit limits the user has expressed

One user-AI pair may have many anchors (typically < 20).
"""

from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class RelationalAnchor(Base):
    __tablename__ = "relational_anchors"
    __table_args__ = (
        Index("ix_anchor_user_ai", "user_id", "ai_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    anchor_type: Mapped[str] = mapped_column(String(30), nullable=False)  # taboo/preference/fear/boundary
    content: Mapped[str] = mapped_column(Text, nullable=False)            # human-readable description
    severity: Mapped[int] = mapped_column(Integer, default=3)             # 1-5 scale
    vector_id: Mapped[str] = mapped_column(String(100), nullable=False)   # ChromaDB reference
    hit_count: Mapped[int] = mapped_column(Integer, default=0)            # times detected as active

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )
