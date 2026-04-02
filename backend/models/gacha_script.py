from datetime import datetime
from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, func
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
