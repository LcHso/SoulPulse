"""
SoulPulse 故事/快拍模型

定义 AI 角色发布的临时内容数据结构，类似 Instagram Stories：
- 内容信息：视频 URL、文案
- 时效控制：创建时间、过期时间
- 关联关系：所属 AI 角色

设计说明：
- 故事是临时性内容，到期后自动删除
- 默认过期时间为 24 小时（可通过配置调整）
- 用于增加 AI 角色的"生活感"和互动频率
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Story(Base):
    """
    故事/快拍数据模型

    AI 角色发布的临时视频内容，类似 Instagram Stories。
    具有时效性，过期后自动清理。

    表名: stories

    字段说明:
        id: 故事唯一标识（自增主键）
        ai_id: 所属 AI 角色 ID（外键）
        video_url: 视频文件 URL
        caption: 文案内容
        created_at: 发布时间
        expires_at: 过期时间
    """
    __tablename__ = "stories"

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 所属 AI 角色 ID，外键关联并建立索引便于查询
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False, index=True)

    # ── 内容字段 ──────────────────────────────────────────
    # 视频文件 URL：故事的视频内容地址
    video_url: Mapped[str] = mapped_column(String(500), default="")
    # 文案内容：故事的文字描述
    caption: Mapped[str] = mapped_column(Text, default="")

    # ── 时效控制字段 ──────────────────────────────────────────
    # 发布时间：数据库自动生成
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 过期时间：到期后故事自动删除，由 story_cleanup.py 脚本清理
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)