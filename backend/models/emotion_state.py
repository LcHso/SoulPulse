"""
SoulPulse 情绪状态模型

定义用户与 AI 角色关系中的情绪状态数据结构，包括：
- 生理维度：能量值
- 心理维度：愉悦度、激活度、依恋度、安全感

情绪维度说明：
- energy: 能量值（0-100），反映关系的活跃程度
- pleasure: 愉悦度（-1.0 到 1.0），正向或负向情绪
- activation: 激活度（-1.0 到 1.0），情绪的强度
- longing: 依恋度（0.0 到 1.0），对角色的思念程度
- security: 安全感（-1.0 到 1.0），关系的稳定感

设计理念：
- 每个用户-角色组合有独立的情绪状态
- 情绪会随互动内容和时间变化
- 用于生成主动关怀消息的触发条件
"""

from datetime import datetime

from sqlalchemy import Integer, Float, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class EmotionState(Base):
    """
    情绪状态数据模型

    存储用户与特定 AI 角色之间的情绪状态。
    采用多维情绪模型，支持精细化情感计算。

    表名: emotion_states

    索引说明:
        ix_emotion_user_ai: 唯一复合索引（user_id, ai_id）
        确保每个用户-角色组合只有一条情绪状态记录

    字段说明:
        id: 状态唯一标识（自增主键）
        user_id: 用户 ID（外键）
        ai_id: AI 角色 ID（外键）
        energy: 能量值（0-100）
        pleasure: 愉悦度（-1.0 到 1.0）
        activation: 激活度（-1.0 到 1.0）
        longing: 依恋度（0.0 到 1.0）
        security: 安全感（-1.0 到 1.0）
        last_interaction_at: 最后互动时间
        updated_at: 更新时间
    """
    __tablename__ = "emotion_states"
    # 唯一复合索引：确保每对用户-角色只有一个情绪状态
    __table_args__ = (
        Index("ix_emotion_user_ai", "user_id", "ai_id", unique=True),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # AI 角色 ID，外键关联 ai_personas 表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # ── 生理维度 ──────────────────────────────────────────
    # 能量值（0-100）：反映关系的活跃程度和生命力
    energy: Mapped[float] = mapped_column(Float, default=80.0)

    # ── 心理维度（多维情绪模型）──────────────────────────
    # 愉悦度（-1.0 到 1.0）：正向情绪为正值，负向情绪为负值
    pleasure: Mapped[float] = mapped_column(Float, default=0.3)
    # 激活度（-1.0 到 1.0）：情绪的强度和唤醒水平
    activation: Mapped[float] = mapped_column(Float, default=0.2)
    # 依恋度（0.0 到 1.0）：对角色的思念和依恋程度
    longing: Mapped[float] = mapped_column(Float, default=0.0)
    # 安全感（-1.0 到 1.0）：关系的稳定感和信任度
    security: Mapped[float] = mapped_column(Float, default=0.5)

    # ── 时间戳字段 ──────────────────────────────────────────
    # 最后互动时间：用于计算情绪衰减
    last_interaction_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    # 更新时间：记录情绪状态的最后修改时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )