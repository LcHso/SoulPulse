"""
SoulPulse 聊天消息模型

定义用户与 AI 角色之间的单条消息数据结构，包括：
- 基本信息：发送者角色、消息内容
- 类型分类：普通聊天/主动私信/系统消息
- 上下文关联：事件标签、帖子上下文
- 投递状态：是否已送达
- 摘要分组：关联的聊天摘要

消息角色说明：
- role="user": 用户发送的消息
- role="assistant": AI 角色的回复

消息类型说明：
- message_type="chat": 普通聊天消息
- message_type="proactive_dm": AI 主动发送的私信
- message_type="system": 系统消息

用途：
- 聊天历史持久化
- 多轮对话上下文
- 主动私信投递追踪
"""

from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class ChatMessage(Base):
    """
    聊天消息数据模型

    存储用户与 AI 角色之间的每一条消息。
    支持聊天历史查询、多轮对话上下文构建、主动私信追踪。

    表名: chat_messages

    索引说明:
        ix_chatmsg_user_ai_id: 复合索引（user_id, ai_id, id）
        用于快速查询特定用户-角色的消息历史

    字段说明:
        id: 消息唯一标识（自增主键）
        user_id: 用户 ID（外键）
        ai_id: AI 角色 ID（外键）
        role: 消息角色（user/assistant）
        content: 消息内容
        message_type: 消息类型（chat/proactive_dm/system）
        event: 事件标签（主动私信触发事件）
        post_context: 帖子上下文（关联帖子 ID）
        delivered: 投递状态（0=未送达, 1=已送达）
        summary_group: 摘要分组 ID（外键）
        created_at: 发送时间
    """
    __tablename__ = "chat_messages"
    # 复合索引：便于按用户-角色查询消息历史
    __table_args__ = (
        Index("ix_chatmsg_user_ai_id", "user_id", "ai_id", "id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # AI 角色 ID，外键关联 ai_personas 表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # ── 消息内容字段 ──────────────────────────────────────────
    # 消息角色："user"（用户）或 "assistant"（AI 角色）
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # 消息文本内容
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 消息类型："chat"（普通聊天）/ "proactive_dm"（主动私信）/ "system"（系统消息）
    message_type: Mapped[str] = mapped_column(String(30), default="chat")

    # ── 上下文关联字段 ──────────────────────────────────────────
    # 事件标签：用于主动私信，记录触发事件（如"长时间未互动"、"情绪波动"）
    event: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # 帖子上下文：记录消息关联的帖子（如评论回复场景）
    post_context: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── 投递状态字段 ──────────────────────────────────────────
    # 投递状态：0=未送达（等待推送）, 1=已送达
    delivered: Mapped[int] = mapped_column(Integer, default=1)
    # 摘要分组：关联的聊天摘要 ID，用于上下文压缩
    summary_group: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("chat_summaries.id"), nullable=True,
    )

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
    )