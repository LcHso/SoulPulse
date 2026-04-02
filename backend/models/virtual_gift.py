from datetime import datetime
from sqlalchemy import String, Integer, Float, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class VirtualGift(Base):
    __tablename__ = "virtual_gifts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon_url: Mapped[str] = mapped_column(String(500), default="")
    energy_recovery: Mapped[float] = mapped_column(Float, default=0.0)
    gem_cost: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = mapped_column(String(50), default="general", index=True)
    is_active: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
