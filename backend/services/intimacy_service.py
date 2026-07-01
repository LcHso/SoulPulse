"""
亲密度服务模块 - 回温加成与衰减状态管理

================================================================================
功能概述
================================================================================
本模块封装亲密度分数变更的核心逻辑，包括：
- apply_intimacy_gain(): 统一的亲密度加分函数，支持回温加成（1.5x）
- 衰减状态的自动清除：当回温次数用尽时，自动退出衰减状态
- 最后互动时间的更新

================================================================================
设计理念
================================================================================
将亲密度加分逻辑从 chat_service.py 和其他分散的位置统一收敛到此处，
确保所有加分路径都经过回温加成检测，避免逻辑遗漏。

================================================================================
主要组件
================================================================================
- apply_intimacy_gain(): 核心加分函数，自动处理回温加成与衰减状态清除
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from models.interaction import Interaction

logger = logging.getLogger(__name__)

# 回温加成倍率：衰减中的用户回归时，前 N 次互动享受 1.5x 亲密度加成
RETURN_BONUS_MULTIPLIER = 1.5

# 初始回温加成次数：用户回归时获得的加成次数上限
INITIAL_RETURN_BONUS = 3

# 亲密度上限
INTIMACY_CAP = 10.0


async def apply_intimacy_gain(
    db: AsyncSession,
    interaction: Interaction,
    base_gain: float,
) -> float:
    """
    为 user-AI pair 应用亲密度加分，支持回温加成。

    当用户从衰减状态回归时，前 3 次互动享受 1.5 倍亲密度加成。
    加成次数用尽后，自动清除衰减状态。

    处理流程：
        1. 检查是否处于衰减状态且有回温加成次数
        2. 计算实际加分数（可能有 1.5x 加成）
        3. 更新亲密度分数（上限 10.0）
        4. 更新 last_interaction_at
        5. 扣减回温加成次数
        6. 如果回温次数归零，清除衰减状态
        7. 返回实际加分数

    Args:
        db: 异步数据库会话
        interaction: Interaction 对象（已加载）
        base_gain: 基础亲密度加分值（例如 0.2）

    Returns:
        float: 实际应用的加分数（可能大于 base_gain，如果有回温加成）
    """
    actual_gain = base_gain

    # ── 回温加成检测 ────────────────────────────────────────────────────
    if interaction.is_decaying and interaction.return_bonus_remaining > 0:
        actual_gain = base_gain * RETURN_BONUS_MULTIPLIER
        interaction.return_bonus_remaining -= 1

        logger.info(
            "Return bonus applied for user=%d ai=%d: %.2f -> %.2f "
            "(remaining: %d)",
            interaction.user_id,
            interaction.ai_id,
            base_gain,
            actual_gain,
            interaction.return_bonus_remaining,
        )

    # ── 回温次数归零 → 清除衰减状态 ──────────────────────────────────────
    if interaction.return_bonus_remaining <= 0 and interaction.is_decaying:
        interaction.is_decaying = False
        interaction.decay_started_at = None
        logger.info(
            "Decay cleared for user=%d ai=%d (return bonus exhausted)",
            interaction.user_id,
            interaction.ai_id,
        )

    # ── 更新亲密度分数（上限 10.0）────────────────────────────────────────
    current_score = float(interaction.intimacy_score or 0.0)
    new_score = min(current_score + actual_gain, INTIMACY_CAP)
    interaction.intimacy_score = new_score

    # ── 更新最后互动时间 ─────────────────────────────────────────────────
    interaction.last_interaction_at = datetime.now(timezone.utc)

    return actual_gain


async def on_user_return(
    db: AsyncSession,
    interaction: Interaction,
) -> None:
    """
    当衰减中的用户回归时，初始化回温加成次数。

    此函数应在用户发送消息时、亲密度加分之前调用。
    它会将 return_bonus_remaining 设为初始值（3），
    后续的 apply_intimacy_gain 会逐次扣减。

    注意：此函数是幂等的——如果 return_bonus_remaining 已经 > 0，
    不会重置（避免每次消息都重置计数器）。

    Args:
        db: 异步数据库会话
        interaction: Interaction 对象（已加载）
    """
    if interaction.is_decaying and interaction.return_bonus_remaining <= 0:
        interaction.return_bonus_remaining = INITIAL_RETURN_BONUS
        logger.info(
            "Return bonus initialized for user=%d ai=%d (%d charges)",
            interaction.user_id,
            interaction.ai_id,
            INITIAL_RETURN_BONUS,
        )
