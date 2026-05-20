"""
SoulPulse 世界事件模型

定义影响 AI 角色行为、内容和情绪的全局事件，例如：
- 节假日（春节、中秋）
- 季节变化
- 故事弧线（专辑发布、巡演）
- 演唱会/音乐节/纪念日

事件可以指定影响范围（affected_persona_ids）、情绪修正值
（mood_modifier_json）以及内容生成指令（content_directive），
被情绪调度器和聊天服务消费，用于在系统提示中注入"当前事件"上下文。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class WorldEvent(Base):
    """
    世界事件数据模型

    表名: world_events
    """

    __tablename__ = "world_events"

    # 事件唯一标识
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # 事件类型：holiday / season / story_arc / concert / festival / anniversary
    event_type: Mapped[str] = mapped_column(String(50))
    # 事件标题，用于展示
    title: Mapped[str] = mapped_column(String(200))
    # 详细描述（可选）
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 事件开始时间
    start_date: Mapped[datetime] = mapped_column(DateTime)
    # 事件结束时间（可选，None 表示长期事件）
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 受影响的角色 ID 列表，例如 [1, 3, 6]
    affected_persona_ids: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    # 情绪修正值，例如 {"energy": 10, "pleasure": 0.2}
    mood_modifier_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # 内容生成指令：在事件期间用于 post / DM / chat 的额外指引
    content_directive: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 是否激活
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
