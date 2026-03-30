"""User FCM Token model for storing device tokens."""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class UserFcmToken(Base):
    """Stores FCM device tokens for push notifications.

    A user can have multiple tokens (multiple devices).
    Tokens are registered when the app starts and should be removed on logout.
    """
    __tablename__ = "user_fcm_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    device_name: Mapped[str] = mapped_column(String(100), nullable=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=True)  # 'android', 'ios', 'web'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())