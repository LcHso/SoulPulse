"""
SoulPulse 服装与场景配置模型 (Plan Task 2)

定义 AI 角色可穿戴的多套造型 / 场景，支撑：
- 情绪驱动的视觉变化（开心 → 出门正装；低落 → 居家睡衣）
- 节日/事件驱动的造型轮换
- 亲密度门槛解锁的私密造型
- 宝石付费购买的高级造型 (商业化)
- 玩家收藏与衣橱系统

每条记录对应某个 persona_id 下的一套造型，
visual_prompt_override 用于在图片生成前替换角色默认的服饰 tag，
scene_prompt 用于补充环境/背景描述。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import Base


class OutfitConfig(Base):
    """
    服装/场景配置

    表名: outfit_configs

    字段:
        id: 主键
        persona_id: AI 角色 ID
        outfit_name: 造型名称（如 "舞台装", "居家睡衣", "运动服"）
        category: 造型分类
            daily / formal / seasonal / event / intimate / workout / sleepwear
        visual_prompt_override: 替换默认 visual_prompt_tags 的服饰描述
        scene_prompt: 场景/环境描述（可选）
        unlock_condition_json: 解锁条件，参考示例：
            {"type": "free"}
            {"type": "intimacy", "min_value": 50}
            {"type": "gem", "cost": 30}
            {"type": "event", "event_id": 5}
        thumbnail_url: 缩略图 URL（衣橱预览）
        is_default: 是否为该角色的默认服装
        is_active: 是否启用（软删除标志）
        sort_order: 排序权重（越小越靠前）
        created_at: 创建时间
    """

    __tablename__ = "outfit_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    persona_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_personas.id"), index=True
    )
    outfit_name: Mapped[str] = mapped_column(String(100))
    # daily / formal / seasonal / event / intimate / workout / sleepwear
    category: Mapped[str] = mapped_column(String(50), index=True)
    visual_prompt_override: Mapped[str] = mapped_column(Text)
    scene_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unlock_condition_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserOutfitUnlock(Base):
    """
    用户已解锁的造型记录

    表名: user_outfit_unlocks

    每个 (user_id, outfit_id) 组合唯一，避免重复发放。
    付费/亲密度达标/事件参与等行为都会写入一条记录。
    """

    __tablename__ = "user_outfit_unlocks"
    __table_args__ = (
        UniqueConstraint("user_id", "outfit_id", name="uq_user_outfit"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), index=True
    )
    outfit_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("outfit_configs.id"), index=True
    )
    unlocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
