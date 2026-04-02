"""
SoulPulse 用户-角色互动关系模型

定义用户与 AI 角色之间的互动状态数据结构，包括：
- 亲密度评分：衡量关系的深度
- 聊天摘要：最近的对话概况
- 特殊昵称：用户对角色的专属称呼

亲密度系统说明：
- intimacy_score：0-100 的评分，随互动增加
- 用于解锁特殊功能和触发主动消息

特殊昵称功能：
- special_nickname：用户给角色起的专属昵称
- nickname_proposed：是否已提议昵称（避免重复）
- 增强个性化体验和情感连接

设计用途：
- 跟踪用户-角色关系的进展
- 支持亲密度相关的功能解锁
- 为主动关怀提供触发条件
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, Float, Text, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Interaction(Base):
    """
    用户-角色互动关系数据模型

    存储用户与特定 AI 角色的互动状态和亲密度信息。

    表名: interactions

    字段说明:
        id: 关系唯一标识（自增主键）
        user_id: 用户 ID（外键，建立索引）
        ai_id: AI 角色 ID（外键，建立索引）
        intimacy_score: 亲密度评分（0-100）
        last_chat_summary: 最近聊天摘要
        special_nickname: 特殊昵称（可选）
        nickname_proposed: 是否已提议昵称
        updated_at: 更新时间
    """
    __tablename__ = "interactions"

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联并建立索引便于查询用户的角色列表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    # AI 角色 ID，外键关联并建立索引便于查询角色的用户列表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False, index=True)

    # ── 亲密度系统字段 ──────────────────────────────────────────
    # 亲密度评分：0-100，随聊天频率和内容质量增加
    # 用于解锁密友内容、触发主动消息等功能
    intimacy_score: Mapped[float] = mapped_column(Float, default=0.0)
    # 最近聊天摘要：LLM 生成的对话概况，便于快速了解聊天主题
    last_chat_summary: Mapped[str] = mapped_column(Text, default="")

    # ── 特殊昵称系统字段 ──────────────────────────────────────────
    # 特殊昵称：用户给角色起的专属称呼，增强情感连接
    special_nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, default=None)
    # 是否已提议昵称：避免 AI 重复提议昵称（SQLite 无布尔类型，用 Integer 模拟）
    nickname_proposed: Mapped[bool] = mapped_column(Integer, default=0)

    # ── 时间戳字段 ──────────────────────────────────────────
    # 更新时间：记录互动状态的最后修改时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )