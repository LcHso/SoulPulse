"""
SoulPulse 故事浏览记录模型

定义用户查看故事的记录数据结构：
- 基本信息：用户 ID、故事 ID
- 创建时间：查看时间

设计用途：
- 跟踪用户是否已查看某故事
- 实现故事的已读/未读状态显示
- 防止重复记录同一用户对同一故事的查看
"""

from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class StoryView(Base):
    """
    故事浏览记录数据模型

    存储用户查看故事的记录，用于实现已读/未读指示。

    表名: story_views

    约束说明:
        uq_user_story_view: 唯一约束（user_id, story_id）
        确保用户对同一故事只有一条查看记录

    索引说明:
        ix_storyview_user: 用户索引，便于查询用户的查看历史

    字段说明:
        id: 查看记录唯一标识（自增主键）
        user_id: 用户 ID（外键）
        story_id: 故事 ID（外键）
        created_at: 查看时间
    """
    __tablename__ = "story_views"
    # 唯一约束：防止重复记录
    __table_args__ = (
        UniqueConstraint("user_id", "story_id", name="uq_user_story_view"),
        Index("ix_storyview_user", "user_id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # 故事 ID，外键关联 stories 表
    story_id: Mapped[int] = mapped_column(Integer, ForeignKey("stories.id"), nullable=False)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())