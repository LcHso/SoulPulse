"""
SoulPulse 角色剧情弧模型

定义 AI 角色的长线剧情弧（Character Arc），按阶段推进剧情。
每个剧情弧绑定一个 persona，包含按顺序的多个阶段（phases），
每个阶段提供 prompt_overlay（系统提示叠加层）、duration_days
（持续天数）以及触发条件（trigger_condition）。

情绪调度器会定期检查活跃剧情弧的当前阶段，根据 started_at 与
duration_days 推进到下一阶段；聊天服务在系统提示中注入当前阶段
的 prompt_overlay，让回复带上剧情色彩。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, JSON, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class CharacterArc(Base):
    """
    角色剧情弧数据模型

    表名: character_arcs
    """

    __tablename__ = "character_arcs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 关联的 AI 角色 ID
    persona_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"))
    # 剧情弧名称，例如 "StarLin's Solo Album Journey"
    arc_name: Mapped[str] = mapped_column(String(200))
    # 当前阶段索引（0 起），用于在 phase_config_json 中定位
    current_phase: Mapped[int] = mapped_column(Integer, default=0)
    # 阶段配置 JSON 数组，每个阶段示例：
    # {
    #     "name": "preparation",
    #     "prompt_overlay": "...",
    #     "duration_days": 7,
    #     "trigger_condition": {...}
    # }
    phase_config_json: Mapped[list] = mapped_column(JSON, default=list)
    # 是否激活
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 弧线开始时间（用于计算阶段是否到期）
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 弧线完成时间
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
