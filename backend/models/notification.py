"""
SoulPulse 通知模型

定义用户通知的数据结构，包括：
- 基本信息：通知类型、标题、内容
- 关联数据：导航用的 JSON 数据
- 状态标识：是否已读

通知类型说明：
- comment_reply: 评论回复通知
- proactive_dm: AI 主动私信通知
- intimacy_upgrade: 亲密度升级通知
- new_post: 新帖子发布通知

设计用途：
- 推送系统通知和互动提醒
- 支持用户点击跳转到相关页面
- 通过 Firebase 实现离线推送
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Notification(Base):
    """
    用户通知数据模型

    存储系统通知和互动提醒，支持站内通知和推送。

    表名: notifications

    索引说明:
        ix_notification_user_read: 复合索引（user_id, is_read）
        便于查询用户的未读通知列表

    字段说明:
        id: 通知唯一标识（自增主键）
        user_id: 用户 ID（外键）
        type: 通知类型
        title: 通知标题
        body: 通知内容
        data_json: 导航数据（JSON）
        is_read: 是否已读
        created_at: 创建时间
    """
    __tablename__ = "notifications"
    # 复合索引：便于查询用户的未读通知
    __table_args__ = (
        Index("ix_notification_user_read", "user_id", "is_read"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)

    # ── 通知内容字段 ──────────────────────────────────────────
    # 通知类型：comment_reply（评论回复）/ proactive_dm（主动私信）/ intimacy_upgrade（亲密度升级）/ new_post（新帖子）
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 通知标题：简短描述
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # 通知正文：详细内容
    body: Mapped[str] = mapped_column(Text, default="")
    # 导航数据：JSON 格式，用于点击通知后跳转到相关页面
    # 示例：{"ai_id": 1, "post_id": 123}
    data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # ── 状态字段 ──────────────────────────────────────────
    # 是否已读：0=未读, 1=已读
    is_read: Mapped[int] = mapped_column(Integer, default=0)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())