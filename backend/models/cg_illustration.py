"""
SoulPulse CG 插画模型

CG (Computer Graphics) 插画用于关键剧情场景的高质量画面，
是乙女向/恋爱模拟游戏的核心收集要素之一。

特点：
- 比日常立绘更精致（更高分辨率、更复杂构图）
- 通常与剧情节点或亲密度等级绑定
- 支持解锁条件（亲密度、钻石、限时活动等）
- 用户收集后会在画廊中展示
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    JSON,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class CGIllustration(Base):
    """
    CG 插画数据模型

    表名: cg_illustrations

    字段说明:
        id: 主键
        persona_id: 所属 AI 角色 ID（外键）
        scene_id: 关联剧情场景 ID（可选）
        title: 插画标题
        description: 插画描述
        image_url: 高清图 URL
        thumbnail_url: 缩略图 URL
        unlock_condition: 解锁条件 JSON
            示例: {"type": "intimacy", "value": 50}
                  {"type": "gem", "value": 30}
        is_collected: 默认未收藏（具体收藏关系见 user_cg_collections）
        quality_tier: 品质等级（standard / premium / limited）
        sort_order: 排序顺序
        is_active: 是否启用（软删除）
        created_at: 创建时间
    """
    __tablename__ = "cg_illustrations"

    # ── 主键与外键 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    persona_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_personas.id"), nullable=False, index=True
    )
    # 可选关联的聊天/剧情场景 ID
    scene_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── 内容字段 ──────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── 解锁与收集字段 ──────────────────────────────────────────
    # 解锁条件，例如 {"type": "intimacy", "value": 50} 或 {"type": "gem", "value": 30}
    unlock_condition: Mapped[dict] = mapped_column(JSON, default=dict)
    # 默认未收藏（per-user 收藏状态见 user_cg_collections 表）
    is_collected: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 品质与展示字段 ──────────────────────────────────────────
    # 品质等级：standard（标准）/ premium（精品）/ limited（限定）
    quality_tier: Mapped[str] = mapped_column(String(20), default="standard")
    # 画廊排序顺序（数值越小越靠前）
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # 是否启用（软删除标志）
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
