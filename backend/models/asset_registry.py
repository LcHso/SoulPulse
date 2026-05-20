"""
Asset Registry Model - 视觉资产注册表

Central registry for tracking all visual assets with versioning and lifecycle management.
Supports:
- Asset type classification (avatar, post, story, outfit, cg, background, expression)
- Version control with rollback capability
- Review workflow (draft -> review -> active -> archived)
- Visual consistency scoring (face similarity)
- Metadata tracking (dimensions, file_size, generation_params, model_used)
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    Text,
    Float,
    DateTime,
    ForeignKey,
    JSON,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class AssetRegistry(Base):
    """
    视觉资产注册表数据模型

    表名: asset_registry

    字段说明:
        id: 主键
        asset_type: 资产类型 (avatar, post, story, outfit, cg, background, expression)
        persona_id: 关联的 AI 角色 ID（可选）
        version: 版本号
        url: 资产 URL
        thumbnail_url: 缩略图 URL
        metadata_json: 元数据 (dimensions, file_size, generation_params, model_used)
        status: 生命周期状态 (draft, review, active, archived)
        consistency_score: 视觉一致性分数 (0.0-1.0)
        review_notes: 审核备注
        created_by: 创建者标识
        created_at: 创建时间
        updated_at: 更新时间
    """
    __tablename__ = "asset_registry"

    # ── 主键与外键 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)
    persona_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("ai_personas.id"),
        nullable=True,
    )

    # ── 版本控制 ──────────────────────────────────────────
    version: Mapped[int] = mapped_column(Integer, default=1)

    # ── 资产 URL ──────────────────────────────────────────
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # ── 元数据 ──────────────────────────────────────────
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # ── 生命周期状态 ──────────────────────────────────────────
    status: Mapped[str] = mapped_column(String(20), default="draft")

    # ── 一致性分数 ──────────────────────────────────────────
    consistency_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # ── 审核与备注 ──────────────────────────────────────────
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
