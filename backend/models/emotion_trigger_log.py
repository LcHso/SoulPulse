"""
SoulPulse 情绪触发日志模型

定义情绪驱动的主动消息触发记录数据结构：
- 基本信息：触发类型、触发时间
- 关联关系：用户、AI 角色

触发类型说明：
- 记录各类情绪触发的主动消息
- 用于冷却控制，避免频繁发送
- 用于审计和分析触发效果

设计用途：
- 防止主动消息过度发送
- 分析情绪触发的有效性
- 优化主动关怀策略
"""

from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class EmotionTriggerLog(Base):
    """
    情绪触发日志数据模型

    记录情绪驱动的主动消息触发事件，用于冷却控制和审计。

    表名: emotion_trigger_logs

    索引说明:
        ix_trigger_user_ai_type: 复合索引（user_id, ai_id, trigger_type）
        便于查询特定用户-角色的特定类型触发记录

    字段说明:
        id: 日志唯一标识（自增主键）
        user_id: 用户 ID（外键）
        ai_id: AI 角色 ID（外键）
        trigger_type: 触发类型
        triggered_at: 触发时间
    """
    __tablename__ = "emotion_trigger_logs"
    # 复合索引：便于查询特定类型触发记录
    __table_args__ = (
        Index("ix_trigger_user_ai_type", "user_id", "ai_id", "trigger_type"),
    )

    # ── 基本标识字段 ──────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 用户 ID，外键关联 users 表
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    # AI 角色 ID，外键关联 ai_personas 表
    ai_id: Mapped[int] = mapped_column(Integer, ForeignKey("ai_personas.id"), nullable=False)

    # ── 触发信息字段 ──────────────────────────────────────────
    # 触发类型：标识主动消息的触发原因
    # 示例："long_time_no_chat"、"emotion_drop"、"intimacy_milestone"
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 触发时间：记录触发发生的具体时间
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())