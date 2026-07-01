"""
SoulPulse 主动 DM 日志模型

记录「思念触发」主动私信系统的完整日志，用于：
- 追踪每条主动 DM 的触发原因（trigger_type）
- 关联引用的记忆 ID（memory_refs）
- 追踪用户是否回复（user_replied / replied_at）
- 后续分析与优化触发策略

触发类型说明：
- longing:          思念值 > 0.7 时触发
- memory_care:      基于用户记忆事件发送关怀
- late_night:       深夜时段特殊触发（未来扩展）
- anniversary:      特殊日期/纪念日触发（未来扩展）

设计用途：
- 为产品分析提供主动 DM 效果数据
- 支持 A/B 测试不同触发策略
- 与 proactive_dms（旧模型）互补，提供更细粒度的追踪
"""

from datetime import datetime

from sqlalchemy import (
    Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ProactiveDMLog(Base):
    """
    主动 DM 日志数据模型

    每次「思念触发」系统发送 DM 时写入一条记录。
    与 proactive_dms（旧表）和 chat_messages 形成三层关联：
      proactive_dm_logs.message_id -> chat_messages.id
      proactive_dm_logs.memory_refs -> [memory_entry.id, ...]

    表名: proactive_dm_logs

    索引说明:
        ix_pdmlog_user_char: 复合索引（user_id, character_id）
        便于查询特定用户-角色的主动 DM 历史

    字段说明:
        id:              日志唯一标识（自增主键）
        user_id:         用户 ID（外键）
        character_id:    AI 角色 ID（外键）
        message_id:      关联的 chat_messages.id（可选）
        trigger_type:    触发类型标签
        memory_refs:     引用的记忆 ID 列表（JSON 数组）
        message_text:    DM 消息正文（冗余存储，便于分析）
        user_replied:    用户是否回复了这条 DM
        replied_at:      用户回复的时间
        created_at:      DM 创建时间
    """
    __tablename__ = "proactive_dm_logs"
    __table_args__ = (
        Index("ix_pdmlog_user_char", "user_id", "character_id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    # AI 角色 ID，外键关联 ai_personas 表
    character_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ai_personas.id"), nullable=False,
    )
    # 关联的聊天消息 ID（可选，用于与 chat_messages 建立关联）
    message_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_messages.id"), nullable=True,
    )

    # ── 触发与内容字段 ──────────────────────────────────────────
    # 触发类型：longing / memory_care / late_night / anniversary
    trigger_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # 引用的记忆 ID 列表，格式：[1, 2, 3]
    memory_refs: Mapped[list] = mapped_column(JSON, default=list)
    # DM 消息正文（冗余存储，便于离线分析）
    message_text: Mapped[str] = mapped_column(Text, nullable=False)

    # ── 回复追踪字段 ──────────────────────────────────────────
    # 用户是否回复了这条 DM
    user_replied: Mapped[bool] = mapped_column(Boolean, default=False)
    # 用户回复时间
    replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )
