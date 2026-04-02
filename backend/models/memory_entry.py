"""
SoulPulse 记忆条目模型

定义用户与 AI 角色对话中提取的记忆数据结构，包括：
- 基本信息：用户 ID、AI 角色 ID、记忆内容
- 类型分类：事实记忆/情感记忆
- 向量引用：ChromaDB 中的向量 ID

记忆类型说明：
- memory_type="fact": 事实记忆（用户说过的事实信息）
- memory_type="emotion": 情感记忆（用户的情感表达）

用途：
- AI 角色在对话中引用用户的过往信息
- 实现个性化对话体验
- 通过向量检索快速匹配相关记忆
"""

from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class MemoryEntry(Base):
    """
    记忆条目数据模型

    存储从用户对话中提取的重要信息，供 AI 角色后续对话引用。
    结合 ChromaDB 向量存储，实现语义检索。

    表名: memory_entries

    索引说明:
        ix_memory_user_ai: 复合索引（user_id, ai_id）
        便于查询特定用户-角色的所有记忆

    字段说明:
        id: 记忆唯一标识（自增主键）
        user_id: 用户 ID（外键）
        ai_id: AI 角色 ID（外键）
        content: 记忆内容（提取的关键信息）
        memory_type: 记忆类型（fact/emotion）
        vector_id: ChromaDB 向量 ID
        created_at: 创建时间
    """
    __tablename__ = "memory_entries"
    # 复合索引：便于按用户-角色查询记忆
    __table_args__ = (
        Index("ix_memory_user_ai", "user_id", "ai_id"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # AI 角色 ID，外键关联 ai_personas 表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # ── 内容字段 ──────────────────────────────────────────
    # 记忆内容：从对话中提取的关键信息文本
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 记忆类型："fact"（事实）或 "emotion"（情感）
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # ── 向量引用字段 ──────────────────────────────────────────
    # ChromaDB 向量 ID：用于语义检索，关联向量数据库中的条目
    vector_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # ── 时间戳字段 ──────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())