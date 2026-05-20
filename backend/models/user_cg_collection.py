"""
SoulPulse 用户 CG 收藏关系模型

记录用户已解锁/收藏的 CG 插画，用于：
- 个人画廊展示
- 解锁进度统计（X/N）
- 防止重复发放奖励

唯一约束：每个用户对每张 CG 仅可收藏一次（user_id + cg_id）。
"""

from datetime import datetime

from sqlalchemy import (
    Integer,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class UserCGCollection(Base):
    """
    用户 CG 收藏关系数据模型

    表名: user_cg_collections

    约束说明:
        uq_user_cg: (user_id, cg_id) 唯一约束，防止重复收藏
        ix_user_cg_user: user_id 索引，便于查询用户全部收藏

    字段说明:
        id: 主键
        user_id: 用户 ID（外键）
        cg_id: CG 插画 ID（外键）
        collected_at: 收藏时间
    """
    __tablename__ = "user_cg_collections"
    __table_args__ = (
        UniqueConstraint("user_id", "cg_id", name="uq_user_cg"),
        Index("ix_user_cg_user", "user_id"),
    )

    # ── 主键与外键 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    cg_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cg_illustrations.id"), nullable=False
    )

    # ── 时间戳字段 ──────────────────────────────────────────
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
