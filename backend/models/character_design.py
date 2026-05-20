"""
SoulPulse 角色设计稿模型

存储 AI 角色的官方美术设定（Character Design Sheet），用于：
- 锁定角色三视图（正面/侧面/背面）
- 表情包参考（喜怒哀乐等）
- 标志性配色方案（signature color palette）
- 多套服装设定（outfit designs）
- 美术指导备注与风格参考图

每个 AI 角色对应唯一的一份角色设定（unique persona_id），
用于在生成 CG 插画与日常立绘时确保视觉一致性。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    JSON,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class CharacterDesign(Base):
    """
    角色设计稿数据模型

    表名: character_designs

    字段说明:
        id: 主键
        persona_id: AI 角色 ID（外键，唯一）
        design_sheet_urls: 三视图（正面/侧面/背面）URL 列表
        expression_sheet_url: 表情包参考图 URL
        color_palette_json: 标志性配色方案 JSON
        outfit_designs_json: 服装设定 JSON 数组
        artist_notes: 美术指导备注
        style_reference_urls: 风格参考图 URL 列表
        created_at: 创建时间
        updated_at: 更新时间
    """
    __tablename__ = "character_designs"

    # ── 主键与外键 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)
    # 关联的 AI 角色 ID，每个角色仅有一份设定
    persona_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("ai_personas.id"),
        nullable=False,
        unique=True,
    )

    # ── 设计稿核心字段 ──────────────────────────────────────────
    # 三视图 URL 列表（正面/侧面/背面）
    design_sheet_urls: Mapped[list] = mapped_column(JSON, default=list)
    # 表情包参考图 URL
    expression_sheet_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # 标志性配色方案，例如 {"primary": "#1A2B3C", "secondary": "#FFD700"}
    color_palette_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # 服装设定数组，每项为一套完整造型的视觉描述
    outfit_designs_json: Mapped[list] = mapped_column(JSON, default=list)

    # ── 辅助说明字段 ──────────────────────────────────────────
    # 美术指导备注（自由文本）
    artist_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 风格参考图 URL 列表（如灵感板）
    style_reference_urls: Mapped[list] = mapped_column(JSON, default=list)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
