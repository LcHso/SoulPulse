"""
SoulPulse 关注关系模型

定义用户关注 AI 角色的关系数据结构：
- 基本信息：用户 ID、AI 角色 ID
- 创建时间：关注时间

设计用途：
- 用户可以关注感兴趣的 AI 角色
- 关注后可以在信息流看到角色的帖子
- 用于筛选和推荐逻辑
"""

from datetime import datetime

from sqlalchemy import Integer, DateTime, ForeignKey, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Follow(Base):
    """
    关注关系数据模型

    存储用户对 AI 角色的关注关系。

    表名: follows

    约束说明:
        uq_user_ai_follow: 唯一约束（user_id, ai_id）
        确保用户不能重复关注同一角色

    索引说明:
        ix_follow_user: 用户索引，便于查询用户的关注列表
        ix_follow_ai: 角色索引，便于查询角色的粉丝列表

    字段说明:
        id: 关注关系唯一标识（自增主键）
        user_id: 用户 ID（外键）
        ai_id: AI 角色 ID（外键）
        created_at: 关注时间
    """
    __tablename__ = "follows"
    # 唯一约束：防止重复关注
    __table_args__ = (
        UniqueConstraint("user_id", "ai_id", name="uq_user_ai_follow"),
        Index("ix_follow_user", "user_id"),
        Index("ix_follow_ai", "ai_id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # AI 角色 ID，外键关联 ai_personas 表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())