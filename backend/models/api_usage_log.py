from datetime import datetime
from sqlalchemy import String, Integer, Float, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from core.database import Base


class ApiUsageLog(Base):
    __tablename__ = "api_usage_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), default="")
    request_tokens: Mapped[int] = mapped_column(Integer, default=0)
    response_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    success: Mapped[int] = mapped_column(Integer, default=1)
    error_message: Mapped[str] = mapped_column(Text, default="")
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
