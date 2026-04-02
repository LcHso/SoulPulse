"""
SoulPulse 主动私信模型

定义 AI 角色主动发送给用户的关怀消息数据结构：
- 基本信息：触发事件、消息内容
- 关联关系：用户、AI 角色
- 发送时间：创建时间

触发事件说明：
- 事件类型包括：长时间未互动、情绪波动、特殊日期等
- 用于追踪主动消息的触发原因

设计用途：
- 实现主动关怀功能
- 增强用户黏性和情感连接
- 与聊天消息模型配合使用
"""

from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ProactiveDM(Base):
    """
    主动私信数据模型

    存储 AI 角色主动发送给高亲密度用户的关怀消息。
    用于追踪主动关怀的历史记录。

    表名: proactive_dms

    索引说明:
        ix_proactive_user_ai: 复合索引（user_id, ai_id）
        便于查询特定用户-角色的主动消息历史

    字段说明:
        id: 消息唯一标识（自增主键）
        user_id: 用户 ID（外键）
        ai_id: AI 角色 ID（外键）
        event: 触发事件
        message: 消息内容
        created_at: 创建时间
    """
    __tablename__ = "proactive_dms"
    # 复合索引：便于查询特定用户-角色的主动消息
    __table_args__ = (
        Index("ix_proactive_user_ai", "user_id", "ai_id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # AI 角色 ID，外键关联 ai_personas 表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # ── 消息内容字段 ──────────────────────────────────────────
    # 触发事件：主动消息的触发原因
    # 示例："long_time_no_chat"（长时间未互动）、"emotion_drop"（情绪下降）
    event: Mapped[str] = mapped_column(String(500), nullable=False)
    # 消息内容：AI 发送的关怀文本
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())