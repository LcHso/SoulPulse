"""
SoulPulse 用户 FCM Token 模型

定义用户设备的 Firebase Cloud Messaging Token 数据结构：
- 基本信息：设备 Token、设备名称、平台类型
- 关联关系：用户 ID
- 时间戳：创建时间、最后使用时间

多设备支持：
- 一个用户可以有多个 Token（多设备）
- App 启动时注册 Token
- 用户登出时移除 Token

平台类型：
- android: Android 设备
- ios: iOS 设备
- web: Web 应用

设计用途：
- 支持 Firebase 推送通知
- 实现离线消息推送
- 多设备推送管理
"""

from datetime import datetime

from sqlalchemy import String, Integer, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class UserFcmToken(Base):
    """
    用户 FCM Token 数据模型

    存储用户设备的 Firebase Cloud Messaging Token，
    用于推送通知的多设备管理。

    表名: user_fcm_tokens

    字段说明:
        id: Token 记录唯一标识（自增主键）
        user_id: 用户 ID（外键，建立索引）
        token: FCM 设备 Token（唯一，建立索引）
        device_name: 设备名称（可选）
        platform: 平台类型（android/ios/web）
        created_at: 创建时间
        last_used_at: 最后使用时间
    """
    __tablename__ = "user_fcm_tokens"

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表，建立索引便于查询用户的所有设备
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # ── Token 字段 ──────────────────────────────────────────
    # FCM 设备 Token：Firebase 分配的唯一设备标识
    # 唯一约束：每个 Token 只能关联一个用户
    # 建立索引：便于快速查找和去重
    token: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # 设备名称：用户自定义的设备名称（可选）
    device_name: Mapped[str] = mapped_column(String(100), nullable=True)
    # 平台类型："android" / "ios" / "web"
    platform: Mapped[str] = mapped_column(String(20), nullable=True)

    # ── 时间戳字段 ──────────────────────────────────────────
    # 创建时间：Token 注册时间
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 最后使用时间：最后一次推送成功的时间，用于清理无效 Token
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())