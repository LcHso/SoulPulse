"""
SoulPulse 用户设备 Token 模型

定义用户设备推送 Token 的数据结构，用于管理多设备推送能力：
- 基本信息：平台类型（ios/android/web）、推送 Token、设备名称
- 关联关系：用户 ID
- 状态标识：是否激活（is_active）
- 时间戳：注册时间

与现有 user_fcm_tokens 表的关系：
- user_fcm_tokens 是早期 FCM 专用 Token 表
- user_devices 是统一设备管理表，支持更完整的推送系统
- 两者可以并存，逐步迁移

设计用途：
- 统一管理 iOS (APNs)、Android (FCM)、Web 推送 Token
- 支持设备激活/停用
- 支持同一用户多设备推送
"""

from datetime import datetime

from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class UserDevice(Base):
    """
    用户设备推送 Token 数据模型

    存储用户各平台的推送 Token，支持多设备管理。

    表名: user_devices

    唯一约束:
        (user_id, push_token) — 同一用户同一 Token 不重复注册

    字段说明:
        id: 设备记录唯一标识（自增主键）
        user_id: 用户 ID（外键）
        platform: 平台类型（ios/android/web）
        push_token: 推送 Token 字符串
        device_name: 设备名称（可选）
        is_active: 是否激活
        registered_at: 注册时间
    """
    __tablename__ = "user_devices"
    __table_args__ = (
        UniqueConstraint("user_id", "push_token", name="uq_user_push_token"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True,
    )

    # ── 设备信息 ──────────────────────────────────────────
    # 平台类型："ios" / "android" / "web"
    platform: Mapped[str] = mapped_column(String(10), nullable=False)
    # 推送 Token：FCM token / APNs token / Web Push subscription
    push_token: Mapped[str] = mapped_column(String(512), nullable=False)
    # 设备名称：用户自定义或系统获取的设备名
    device_name: Mapped[str] = mapped_column(String(100), nullable=True)

    # ── 状态字段 ──────────────────────────────────────────
    # 是否激活：False 时不向此设备推送
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── 时间戳 ──────────────────────────────────────────
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
