"""
SoulPulse 聊天摘要模型

定义聊天对话的 LLM 生成摘要数据结构：
- 基本信息：摘要内容、消息范围
- 关联关系：用户、AI 角色

摘要机制说明：
- 每 10 条用户消息生成一次摘要
- 新摘要包含旧摘要 + 最近 10 轮对话
- 用于压缩对话上下文，避免 Token 无限增长
- 摘要关联的消息通过 message_range_start/end 标识

设计用途：
- 实现对话上下文的滚动压缩
- 减少 LLM Token 消耗
- 保持长对话的连贯性
"""

from datetime import datetime

from sqlalchemy import Integer, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ChatSummary(Base):
    """
    聊天摘要数据模型

    存储用户与 AI 角色对话的 LLM 生成摘要。
    用于对话上下文压缩，避免长对话的 Token 爆炸。

    表名: chat_summaries

    索引说明:
        ix_chatsummary_user_ai_time: 复合索引（user_id, ai_id, created_at）
        便于按时间查询特定用户-角色的摘要

    字段说明:
        id: 摘要唯一标识（自增主键）
        user_id: 用户 ID（外键）
        ai_id: AI 角色 ID（外键）
        content: 摘要文本
        message_range_start: 起始消息 ID
        message_range_end: 结束消息 ID
        created_at: 创建时间
    """
    __tablename__ = "chat_summaries"
    # 复合索引：便于按时间查询摘要
    __table_args__ = (
        Index("ix_chatsummary_user_ai_time", "user_id", "ai_id", "created_at"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # AI 角色 ID，外键关联 ai_personas 表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # ── 摘要内容字段 ──────────────────────────────────────────
    # 摘要文本：LLM 生成的对话压缩内容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 起始消息 ID：摘要覆盖的第一条消息
    message_range_start: Mapped[int] = mapped_column(Integer, nullable=False)
    # 结束消息 ID：摘要覆盖的最后一条消息
    message_range_end: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )