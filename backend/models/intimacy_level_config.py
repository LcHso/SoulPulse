"""
SoulPulse 亲密度分层行为参数配置模型

定义不同亲密度等级下 AI 角色的行为参数配置，包括：
- LLM 生成参数（temperature、max_tokens、top_p）
- 回复长度限制（min_reply_chars、max_reply_chars）
- 表情策略（emoji_policy）
- 动作描写开关（action_desc）
- 禁止词列表（forbidden_words）
- 允许的亲昵称呼（allowed_affection）
- 主动消息冷却时间（proactive_cooldown_hours）

亲密度系统共 6 个等级：
  Level 0: 陌生人 (Stranger)        — score 0.0-2.9
  Level 1: 熟人 (Acquaintance)      — score 3.0-4.9
  Level 2: 朋友 (Friend)            — score 5.0-5.9
  Level 3: 挚友 (Close Friend)      — score 6.0-6.9
  Level 4: 密友 (Confidant)         — score 7.0-8.9
  Level 5: 灵魂伴侣 (Soulmate)      — score 9.0-10.0

设计用途：
- 替代原有硬编码的社交边界约束，实现配置化驱动
- 支持通过管理后台动态调整各级参数
- 为 IntimacyConfigResolver 提供数据源
"""

import json
from typing import Optional

from sqlalchemy import String, Integer, Numeric, Boolean, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class IntimacyLevelConfig(Base):
    """
    亲密度等级行为参数配置模型。

    每个等级对应一行配置，定义该等级下 AI 回复的所有行为参数。

    表名: intimacy_level_configs

    字段说明:
        level_id: 等级 ID（0-5，主键）
        level_name: 等级英文名（stranger/acquaintance/friend/close_friend/confidant/soulmate）
        level_name_cn: 等级中文名（陌生人/熟人/朋友/挚友/密友/灵魂伴侣）
        min_score: 该等级最低亲密度分数（含）
        max_score: 该等级最高亲密度分数（含）
        temperature: LLM 生成温度（0.00-1.00）
        max_tokens: LLM 最大生成 token 数
        top_p: LLM top_p 采样参数
        min_reply_chars: 回复最小字符数
        max_reply_chars: 回复最大字符数
        emoji_policy: 表情策略（none/rare/moderate/unlimited）
        action_desc: 是否允许动作描写（全角括号描写）
        forbidden_words: 禁止词列表（JSON 数组）
        allowed_affection: 允许的亲昵称呼列表（JSON 数组）
        proactive_cooldown_hours: 主动消息冷却时间（小时）
    """
    __tablename__ = "intimacy_level_configs"

    # ── 主键与等级标识 ──────────────────────────────────────────
    level_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level_name: Mapped[str] = mapped_column(String(20), nullable=False)
    level_name_cn: Mapped[str] = mapped_column(String(20), nullable=False)

    # ── 亲密度分数区间 ──────────────────────────────────────────
    min_score: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)
    max_score: Mapped[float] = mapped_column(Numeric(3, 1), nullable=False)

    # ── LLM 生成参数 ──────────────────────────────────────────
    temperature: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    top_p: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)

    # ── 回复长度限制 ──────────────────────────────────────────
    min_reply_chars: Mapped[int] = mapped_column(Integer, nullable=False)
    max_reply_chars: Mapped[int] = mapped_column(Integer, nullable=False)

    # ── 行为策略 ──────────────────────────────────────────
    emoji_policy: Mapped[str] = mapped_column(
        String(20), default="none",
    )  # none / rare / moderate / unlimited
    action_desc: Mapped[bool] = mapped_column(Boolean, default=False)

    # ── 词汇与称呼控制 ──────────────────────────────────────────
    forbidden_words: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=False, default=list,
    )
    allowed_affection: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=False, default=list,
    )

    # ── 主动消息 ──────────────────────────────────────────
    proactive_cooldown_hours: Mapped[int] = mapped_column(Integer, default=24)

    # ── 辅助方法 ──────────────────────────────────────────
    def get_forbidden_words(self) -> list[str]:
        """返回禁止词列表（兼容 JSON 字段可能为字符串的情况）。"""
        if isinstance(self.forbidden_words, str):
            return json.loads(self.forbidden_words)
        return self.forbidden_words or []

    def get_allowed_affection(self) -> list[str]:
        """返回允许的亲昵称呼列表。"""
        if isinstance(self.allowed_affection, str):
            return json.loads(self.allowed_affection)
        return self.allowed_affection or []

    def to_dict(self) -> dict:
        """将配置序列化为字典，便于传递给 LLM 参数构建。"""
        return {
            "level_id": self.level_id,
            "level_name": self.level_name,
            "level_name_cn": self.level_name_cn,
            "min_score": float(self.min_score),
            "max_score": float(self.max_score),
            "temperature": float(self.temperature),
            "max_tokens": self.max_tokens,
            "top_p": float(self.top_p),
            "min_reply_chars": self.min_reply_chars,
            "max_reply_chars": self.max_reply_chars,
            "emoji_policy": self.emoji_policy,
            "action_desc": self.action_desc,
            "forbidden_words": self.get_forbidden_words(),
            "allowed_affection": self.get_allowed_affection(),
            "proactive_cooldown_hours": self.proactive_cooldown_hours,
        }
