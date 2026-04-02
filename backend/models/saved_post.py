"""
SoulPulse 收藏帖子模型

定义用户收藏/书签帖子的关系数据结构：
- 基本信息：用户 ID、帖子 ID
- 创建时间：收藏时间

设计用途：
- 用户可以收藏感兴趣的帖子
- 便于后续查看和回顾
- 防止重复收藏同一帖子
"""

from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class SavedPost(Base):
    """
    收藏帖子数据模型

    存储用户对帖子的收藏/书签记录。

    表名: saved_posts

    约束说明:
        uq_user_saved_post: 唯一约束（user_id, post_id）
        确保用户不能重复收藏同一帖子

    索引说明:
        ix_savedpost_user: 用户索引，便于查询用户的收藏列表

    字段说明:
        id: 收藏记录唯一标识（自增主键）
        user_id: 用户 ID（外键）
        post_id: 帖子 ID（外键）
        created_at: 收藏时间
    """
    __tablename__ = "saved_posts"
    # 唯一约束：防止重复收藏
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_user_saved_post"),
        Index("ix_savedpost_user", "user_id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # 帖子 ID，外键关联 posts 表
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id"), nullable=False)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())