"""
SoulPulse 用户点赞模型

定义用户对帖子的点赞关系数据结构：
- 基本信息：用户 ID、帖子 ID
- 创建时间：点赞时间

设计用途：
- 记录用户对帖子的点赞行为
- 防止重复点赞
- 用于帖子点赞数统计
"""

from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class UserLike(Base):
    """
    用户点赞数据模型

    存储用户对帖子的点赞记录。

    表名: user_likes

    约束说明:
        uq_user_post_like: 唯一约束（user_id, post_id）
        确保用户不能重复点赞同一帖子

    索引说明:
        ix_userlike_user: 用户索引，便于查询用户的点赞历史

    字段说明:
        id: 点赞记录唯一标识（自增主键）
        user_id: 用户 ID（外键）
        post_id: 帖子 ID（外键）
        created_at: 点赞时间
    """
    __tablename__ = "user_likes"
    # 唯一约束：防止重复点赞
    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_user_post_like"),
        Index("ix_userlike_user", "user_id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # 帖子 ID，外键关联 posts 表
    post_id: Mapped[int] = mapped_column(Integer, ForeignKey("posts.id"), nullable=False)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())