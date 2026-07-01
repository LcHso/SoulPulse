"""
SoulPulse 通知偏好模型

定义用户的通知偏好设置，包括：
- 各类通知开关：新帖子、主动私信、故事、评论回复、亲密度事件
- 免打扰时段：quiet_hour_start ~ quiet_hour_end
- 单角色覆盖：per_character_overrides JSON 字段

设计理念：
- 每个用户只有一条偏好记录（user_id 为主键）
- 用户注册时自动创建默认记录（全部开启）
- 支持按角色粒度覆盖通知设置
"""

from datetime import datetime, time
from typing import Optional

from sqlalchemy import Integer, String, Boolean, Time, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class NotificationPreference(Base):
    """
    用户通知偏好数据模型

    存储用户对各类推送通知的开关设置和免打扰时段。

    表名: notification_preferences

    字段说明:
        user_id: 用户 ID（主键，外键关联 users 表）
        new_post: 新帖子通知开关
        proactive_dm: 主动私信通知开关
        new_story: 故事/快拍通知开关
        comment_reply: 评论回复通知开关
        intimacy_event: 亲密度事件通知开关
        quiet_hour_start: 免打扰开始时间
        quiet_hour_end: 免打扰结束时间
        per_character_overrides: 按角色覆盖的 JSON 配置
        created_at: 创建时间
    """
    __tablename__ = "notification_preferences"

    # ── 主键：与 users 表一对一 ──────────────────────────────────────────
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), primary_key=True,
    )

    # ── 通知类型开关 ──────────────────────────────────────────
    new_post: Mapped[bool] = mapped_column(Boolean, default=True)
    proactive_dm: Mapped[bool] = mapped_column(Boolean, default=True)
    new_story: Mapped[bool] = mapped_column(Boolean, default=True)
    comment_reply: Mapped[bool] = mapped_column(Boolean, default=True)
    intimacy_event: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── 免打扰时段 ──────────────────────────────────────────
    # 例如 23:00 ~ 07:00 表示夜间不推送
    quiet_hour_start: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    quiet_hour_end: Mapped[Optional[time]] = mapped_column(Time, nullable=True)

    # ── 按角色覆盖配置 ──────────────────────────────────────────
    # JSON 格式，key 为 character_id，value 为覆盖设置
    # 示例: {"5": {"proactive_dm": false}, "12": {"new_post": false}}
    per_character_overrides: Mapped[Optional[str]] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}",
    )

    # ── 时间戳 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
