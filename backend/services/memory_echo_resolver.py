"""
记忆回响解析器 — Memory Echo Resolver

让 AI 在生成 Feed 帖子时，微妙地引用与用户的聊天记忆，
使帖子内容带有"记忆回响"的温度感。

工作原理：
    1. 查询与某个 AI 角色亲密度 >= 5.0（朋友层级）的所有用户
    2. 随机选一个用户，从其长期记忆中提取最近 14 天的 fact 类型记忆
    3. 将记忆格式化为 prompt 注入片段，供帖子文案生成时参考
    4. AI 会以"自己的经历"口吻微妙地融入记忆素材，而非直接引用

设计原则：
    - 亲密度门控：只有关系足够亲密的用户，其记忆才会被回响
    - 自然融入：AI 不会说"你告诉过我"，而是转化为自己的体验
    - 低频率：并非每次发帖都触发，保持自然感

作者：SoulPulse Team
"""

import logging
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, and_

from core.database import async_session
from models.interaction import Interaction
from models.memory_entry import MemoryEntry

logger = logging.getLogger(__name__)

# ── 常量配置 ──────────────────────────────────────────────
# 亲密度阈值：达到此分数的用户记忆才会被回响
INTIMACY_THRESHOLD = 5.0
# 记忆时间窗口：只取最近 N 天的记忆
MEMORY_MAX_AGE_DAYS = 14
# 每个用户提取的记忆条数上限
MEMORY_LIMIT = 3


async def get_high_intimacy_users(
    ai_id: int,
    threshold: float = INTIMACY_THRESHOLD,
) -> list[dict]:
    """
    查询与指定 AI 角色亲密度 >= threshold 的所有用户。

    Args:
        ai_id: AI 角色 ID
        threshold: 亲密度阈值（默认 5.0）

    Returns:
        list[dict]: 包含 user_id 和 intimacy_score 的字典列表
    """
    async with async_session() as db:
        result = await db.execute(
            select(Interaction.user_id, Interaction.intimacy_score).where(
                and_(
                    Interaction.ai_id == ai_id,
                    Interaction.intimacy_score >= threshold,
                )
            )
        )
        rows = result.all()
        return [
            {"user_id": row.user_id, "intimacy_score": row.intimacy_score}
            for row in rows
        ]


async def _fetch_recent_memories(
    user_id: int,
    ai_id: int,
    limit: int = MEMORY_LIMIT,
    max_age_days: int = MEMORY_MAX_AGE_DAYS,
    memory_type: str = "fact",
) -> list[MemoryEntry]:
    """
    从 SQLite 中获取指定用户-角色对的最近记忆。

    直接查询 memory_entries 表，按 created_at 降序排列，
    仅取时间窗口内的 fact 类型记忆。

    Args:
        user_id: 用户 ID
        ai_id: AI 角色 ID
        limit: 返回条数上限
        max_age_days: 最大记忆年龄（天）
        memory_type: 记忆类型（默认 "fact"）

    Returns:
        list[MemoryEntry]: 记忆条目列表
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    async with async_session() as db:
        result = await db.execute(
            select(MemoryEntry).where(
                and_(
                    MemoryEntry.user_id == user_id,
                    MemoryEntry.ai_id == ai_id,
                    MemoryEntry.memory_type == memory_type,
                    MemoryEntry.created_at >= cutoff,
                )
            ).order_by(MemoryEntry.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())


async def resolve_memory_echo(
    ai_id: int,
) -> dict:
    """
    记忆回响解析主函数。

    为指定 AI 角色寻找一个高亲密度用户，提取其最近记忆，
    格式化为可注入帖子生成 prompt 的文本片段。

    Args:
        ai_id: AI 角色 ID

    Returns:
        dict: 包含以下字段：
            - memory_echo_section (str): 注入到 prompt 的记忆回响文本，无则为空串
            - memory_echo_refs (list[dict]): 引用的记忆 ID 和 user_id，用于持久化
            - trigger_type (str): 'memory_echo' 或 'scheduled'
            - source_user_id (int|None): 记忆来源用户 ID
    """
    empty_result = {
        "memory_echo_section": "",
        "memory_echo_refs": [],
        "trigger_type": "scheduled",
        "source_user_id": None,
    }

    try:
        # 1. 查询高亲密度用户
        high_intimacy_users = await get_high_intimacy_users(ai_id)
        if not high_intimacy_users:
            logger.debug(
                "[memory_echo] No users with intimacy >= %.1f for ai_id=%d",
                INTIMACY_THRESHOLD, ai_id,
            )
            return empty_result

        # 2. 随机选一个用户（加权：亲密度越高越容易被选中）
        weights = [u["intimacy_score"] for u in high_intimacy_users]
        chosen = random.choices(high_intimacy_users, weights=weights, k=1)[0]
        chosen_user_id = chosen["user_id"]

        logger.info(
            "[memory_echo] Selected user_id=%d (intimacy=%.1f) for ai_id=%d",
            chosen_user_id, chosen["intimacy_score"], ai_id,
        )

        # 3. 提取该用户的最近 fact 记忆
        memories = await _fetch_recent_memories(
            user_id=chosen_user_id,
            ai_id=ai_id,
            limit=MEMORY_LIMIT,
            max_age_days=MEMORY_MAX_AGE_DAYS,
            memory_type="fact",
        )

        if not memories:
            logger.debug(
                "[memory_echo] No recent fact memories for user_id=%d ai_id=%d",
                chosen_user_id, ai_id,
            )
            return empty_result

        # 4. 格式化为 prompt 注入片段
        seeds = [f"- {m.content}" for m in memories]
        memory_echo_section = (
            "Memory Echo Seeds (things you remember about people close to you):\n"
            + "\n".join(seeds)
            + "\n\n"
            "You may subtly weave ONE of these into your post as your own experience.\n"
            "Never say \"you told me\" or \"remember when you said\". Frame it as YOUR experience.\n"
        )

        # 5. 构建引用记录
        echo_refs = [
            {"memory_id": m.id, "user_id": m.user_id}
            for m in memories
        ]

        logger.info(
            "[memory_echo] Resolved %d memory seeds for ai_id=%d from user_id=%d",
            len(memories), ai_id, chosen_user_id,
        )

        return {
            "memory_echo_section": memory_echo_section,
            "memory_echo_refs": echo_refs,
            "trigger_type": "memory_echo",
            "source_user_id": chosen_user_id,
        }

    except Exception:
        logger.exception("[memory_echo] Failed to resolve for ai_id=%d", ai_id)
        return empty_result


def build_emotion_snapshot(emo_states: list) -> Optional[dict]:
    """
    从情绪状态列表中构建 5D 情绪快照字典。

    计算各维度的均值，用于持久化到帖子的 emotion_snapshot 字段。

    Args:
        emo_states: EmotionState 对象列表

    Returns:
        dict|None: 情绪快照字典，无数据时返回 None
    """
    if not emo_states:
        return None

    n = len(emo_states)
    return {
        "energy": round(sum(s.energy for s in emo_states) / n, 1),
        "pleasure": round(sum(s.pleasure for s in emo_states) / n, 3),
        "activation": round(sum(s.activation for s in emo_states) / n, 3),
        "longing": round(sum(s.longing for s in emo_states) / n, 3),
        "security": round(sum(s.security for s in emo_states) / n, 3),
    }
