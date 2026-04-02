"""
SoulPulse 关系锚点模型

定义用户与 AI 角色关系中的情感敏感点数据结构：
- 锚点类型：禁忌、偏好、恐惧、边界
- 内容描述：具体的敏感点说明
- 严重程度：1-5 级评分
- 向量引用：用于语义匹配

锚点类型说明：
- taboo（禁忌）: 用户不喜欢或会负面反应的话题
- preference（偏好）: 用户特别喜欢或重视的事物
- fear（恐惧）: 用户的焦虑、不安或担忧
- boundary（边界）: 用户明确表达的界限

设计用途：
- 学习用户的情感敏感点
- 防止 AI 触碰用户的禁忌
- 增强 AI 的情感智能和个性化回应
- 通过向量匹配实现语义触发
"""

from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class RelationalAnchor(Base):
    """
    关系锚点数据模型

    存储用户与 AI 角色关系中学习到的情感敏感点。
    用于增强 AI 的情感智能，避免触碰禁忌并识别偏好。

    表名: relational_anchors

    索引说明:
        ix_anchor_user_ai: 复合索引（user_id, ai_id）
        便于查询特定用户-角色的锚点列表

    字段说明:
        id: 锚点唯一标识（自增主键）
        user_id: 用户 ID（外键）
        ai_id: AI 角色 ID（外键）
        anchor_type: 锚点类型（taboo/preference/fear/boundary）
        content: 内容描述
        severity: 严重程度（1-5）
        vector_id: 向量 ID（ChromaDB）
        hit_count: 触发次数
        created_at: 创建时间
        updated_at: 更新时间
    """
    __tablename__ = "relational_anchors"
    # 复合索引：便于查询特定用户-角色的锚点
    __table_args__ = (
        Index("ix_anchor_user_ai", "user_id", "ai_id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # AI 角色 ID，外键关联 ai_personas 表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # ── 锚点内容字段 ──────────────────────────────────────────
    # 锚点类型：taboo（禁忌）/ preference（偏好）/ fear（恐惧）/ boundary（边界）
    anchor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # 内容描述：人类可读的敏感点描述
    # 示例："不喜欢被催促"、"特别在意生日"
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 严重程度：1-5 级，数值越高越重要
    severity: Mapped[int] = mapped_column(Integer, default=3)

    # ── 向量引用字段 ──────────────────────────────────────────
    # ChromaDB 向量 ID：用于语义匹配，关联向量数据库中的条目
    vector_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # 触发次数：记录锚点被检测激活的次数，用于评估重要性
    hit_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
    )