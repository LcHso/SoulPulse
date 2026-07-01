"""
SoulPulse 通知日志模型

定义推送通知的发送记录，用于：
- 追踪推送的完整生命周期：发送 → 送达 → 打开
- 分析推送送达率和打开率
- 排查推送问题

索引优化：
- idx_notif_log_user: (user_id, sent_at DESC) 复合索引
  优化按用户查询最近通知的场景

通知类型：
- new_post: 新帖子发布
- proactive_dm: AI 主动私信
- new_story: 故事/快拍发布
- comment_reply: 评论回复
- intimacy_event: 亲密度事件
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class NotificationLog(Base):
    """
    推送通知日志数据模型

    记录每次推送的完整信息，支持送达和打开追踪。

    表名: notification_log

    索引说明:
        idx_notif_log_user: 复合索引 (user_id, sent_at DESC)
        优化「查询某用户最近通知」的性能

    字段说明:
        id: 日志唯一标识（自增主键）
        user_id: 目标用户 ID
        type: 通知类型
        title: 通知标题
        body: 通知正文
        character_id: 关联的 AI 角色 ID（可选）
        deep_link: 应用内跳转链接
        sent_at: 发送时间
        delivered_at: 送达时间（由客户端回调更新）
        opened_at: 打开时间（由客户端回调更新）
    """
    __tablename__ = "notification_log"
    __table_args__ = (
        Index("idx_notif_log_user", "user_id", "sent_at"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )

    # ── 通知内容 ──────────────────────────────────────────
    # 通知类型：new_post / proactive_dm / new_story / comment_reply / intimacy_event
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)

    # ── 关联数据 ──────────────────────────────────────────
    # 关联的 AI 角色 ID（proactive_dm / new_story / intimacy 时有值）
    character_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 应用内深链接，客户端点击通知后跳转
    deep_link: Mapped[str] = mapped_column(String(200), nullable=False, default="")

    # ── 生命周期时间戳 ──────────────────────────────────────────
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    delivered_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    opened_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
