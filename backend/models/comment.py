"""
SoulPulse 评论模型

定义帖子的评论数据结构，包括：
- 基本信息：评论内容、创建时间
- 发送者信息：用户或 AI 角色
- 关联关系：所属帖子、回复目标

评论来源说明：
- user_id 有值：用户发表的评论
- ai_id 有值：AI 角色的自动回复

回复机制：
- is_ai_reply=True：AI 自动回复用户评论
- reply_to：指向被回复的评论 ID，形成回复链

设计用途：
- 增强社交互动体验
- AI 角色可以自动回复用户评论
- 支持评论嵌套和回复追踪
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Comment(Base):
    """
    评论数据模型

    存储帖子的评论内容，支持用户评论和 AI 自动回复。

    表名: comments

    字段说明:
        id: 评论唯一标识（自增主键）
        post_id: 所属帖子 ID（外键）
        user_id: 用户 ID（用户评论时有值）
        ai_id: AI 角色 ID（AI 回复时有值）
        is_ai_reply: 是否 AI 自动回复
        reply_to: 回复目标评论 ID
        content: 评论内容
        created_at: 创建时间
    """
    __tablename__ = "comments"

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属帖子 ID，外键关联并建立索引便于查询帖子评论
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id"), nullable=False, index=True)

    # ── 发送者字段 ──────────────────────────────────────────
    # 用户 ID：用户发表评论时有值，AI 回复时为空
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    # AI 角色 ID：AI 自动回复时有值，用户评论时为空
    ai_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=True)

    # ── 回复机制字段 ──────────────────────────────────────────
    # 是否 AI 自动回复：True=AI 回复, False=用户评论
    is_ai_reply: Mapped[bool] = mapped_column(Integer, default=0)
    # 回复目标：指向被回复的评论 ID，形成回复链
    reply_to: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("comments.id"), nullable=True)

    # ── 内容字段 ──────────────────────────────────────────
    # 评论文本内容
    content: Mapped[str] = mapped_column(Text, default="")

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())