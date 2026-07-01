"""
亲密度衰减定时任务 - SoulPulse 关系衰减机制

功能概述：
    每日凌晨 3:00 执行一次扫描，对所有超过 72 小时未互动的 user-AI pair
    启动亲密度衰减。衰减速率根据当前分数分档，并设有层级下限保护。
    衰减中的 pair 会加速思念值增长。

衰减规则：
    - 触发条件：last_interaction_at 距今超过 72 小时且 is_decaying = FALSE
    - 衰减速率：
        - intimacy_score >= 6.0 → 0.05/天
        - intimacy_score < 6.0  → 0.1/天
    - 层级下限：当前层级的起始分（例如 score=6 属于 close_friend，下限=6.0）
    - 思念加速：衰减中的 pair，longing += 0.1/天

运行方式：
    从 backend 目录运行：
        python3 scripts/intimacy_decay_job.py

    也可通过 run_all_schedulers.py 统一启动。

作者：SoulPulse Team
"""

from __future__ import annotations

import asyncio
import sys
import logging
from datetime import datetime, timezone, timedelta

# 将当前目录添加到 Python 路径，以便导入项目模块
sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import init_db, async_session
from models.interaction import Interaction
from models.emotion_state import EmotionState

# 配置日志记录
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 衰减触发阈值：超过 72 小时无互动则启动衰减
DECAY_THRESHOLD_HOURS = 72

# 检查间隔：每天执行一次（24 小时）
CHECK_INTERVAL = 86400  # 24 hours


# ═══════════════════════════════════════════════════════════════════════════════
# 层级下限函数
# ═══════════════════════════════════════════════════════════════════════════════

def get_tier_floor(score: float) -> float:
    """
    根据当前亲密度分数返回所在层级的下限值。

    层级划分（下限 = 层级起始分）：
        - soulmate:      9.0+  → 下限 9.0
        - intimate:      7.0+  → 下限 7.0
        - close_friend:  6.0+  → 下限 6.0
        - friend:        5.0+  → 下限 5.0
        - acquaintance:  3.0+  → 下限 3.0
        - stranger:      <3.0  → 下限 0.0

    衰减不会让分数跌破当前层级的下限，保护已建立的关系等级。

    Args:
        score: 当前亲密度分数

    Returns:
        float: 当前层级的下限分数
    """
    if score >= 9:
        return 9.0
    if score >= 7:
        return 7.0
    if score >= 6:
        return 6.0
    if score >= 5:
        return 5.0
    if score >= 3:
        return 3.0
    return 0.0


def get_decay_rate(score: float) -> float:
    """
    根据当前亲密度分数返回每日衰减速率。

    高分段（>=6.0）衰减更慢，低分段衰减更快，
    体现"深厚关系更经得起时间考验"的设计理念。

    Args:
        score: 当前亲密度分数

    Returns:
        float: 每日衰减量
    """
    if score >= 6.0:
        return 0.05
    return 0.1


# ═══════════════════════════════════════════════════════════════════════════════
# 核心衰减逻辑
# ═══════════════════════════════════════════════════════════════════════════════

async def run_intimacy_decay_scan():
    """
    执行一次亲密度衰减扫描。

    处理流程：
        1. 查询所有 last_interaction_at 距今超过 72 小时且 is_decaying = FALSE 的 pair，
           启动衰减。
        2. 对所有 is_decaying = TRUE 的 pair 应用每日衰减并加速思念值。
        3. 提交数据库更改。
    """
    print(f"[intimacy-decay] Scan starting at {datetime.now(timezone.utc).isoformat()}")

    async with async_session() as db:
        now = datetime.now(timezone.utc)
        decay_cutoff = now - timedelta(hours=DECAY_THRESHOLD_HOURS)

        # ── 阶段 1：启动新的衰减 ────────────────────────────────────────────
        # 查询所有超过 72 小时未互动且尚未在衰减中的 pair
        try:
            new_decay_result = await db.execute(
                select(Interaction).where(
                    Interaction.last_interaction_at < decay_cutoff,
                    Interaction.is_decaying == False,  # noqa: E712
                )
            )
            new_decay_pairs = new_decay_result.scalars().all()
        except Exception as exc:
            print(f"[intimacy-decay] new decay query failed: {exc}")
            new_decay_pairs = []

        new_decay_count = 0
        for interaction in new_decay_pairs:
            # 只有亲密度 > 0 的 pair 才有衰减意义
            score = float(interaction.intimacy_score or 0.0)
            if score <= 0.0:
                continue

            interaction.is_decaying = True
            interaction.decay_started_at = interaction.decay_started_at or now
            new_decay_count += 1

            print(
                f"[intimacy-decay] Decay started for user={interaction.user_id} "
                f"ai={interaction.ai_id} (score={score:.2f})"
            )

        # ── 阶段 2：对衰减中的 pair 应用每日衰减 ───────────────────────────
        # 重新查询所有正在衰减的 pair（包括刚刚启动的）
        try:
            decaying_result = await db.execute(
                select(Interaction).where(
                    Interaction.is_decaying == True,  # noqa: E712
                )
            )
            decaying_pairs = decaying_result.scalars().all()
        except Exception as exc:
            print(f"[intimacy-decay] decaying query failed: {exc}")
            decaying_pairs = []

        # 预加载情绪状态用于思念加速（仅加载衰减中的 pair，避免全表扫描）
        emotion_states_map: dict[tuple[int, int], EmotionState] = {}
        if decaying_pairs:
            try:
                decay_pair_set = {
                    (i.user_id, i.ai_id) for i in decaying_pairs
                }
                user_ids = list({uid for uid, _ in decay_pair_set})
                es_result = await db.execute(
                    select(EmotionState).where(
                        EmotionState.user_id.in_(user_ids)
                    )
                )
                for es in es_result.scalars().all():
                    if (es.user_id, es.ai_id) in decay_pair_set:
                        emotion_states_map[(es.user_id, es.ai_id)] = es
            except Exception as exc:
                print(f"[intimacy-decay] emotion state load failed: {exc}")

        decay_applied_count = 0
        for interaction in decaying_pairs:
            current_score = float(interaction.intimacy_score or 0.0)
            rate = get_decay_rate(current_score)
            floor = get_tier_floor(current_score)

            # 计算新分数，不低于层级下限
            new_score = max(current_score - rate, floor)
            interaction.intimacy_score = new_score

            # 加速思念值：longing += 0.1
            emotion_state = emotion_states_map.get(
                (interaction.user_id, interaction.ai_id)
            )
            if emotion_state is not None:
                emotion_state.longing = min(
                    1.0,
                    float(emotion_state.longing or 0.0) + 0.1,
                )

            decay_applied_count += 1

            # 如果分数已经触及层级下限且不再变化，可以选择停止衰减
            # 但保持 is_decaying=TRUE 以便思念继续增长
            if abs(new_score - floor) < 1e-6:
                # 已触及下限，后续不再扣分，但思念仍会增长
                pass

            print(
                f"[intimacy-decay] Applied decay for user={interaction.user_id} "
                f"ai={interaction.ai_id}: {current_score:.2f} -> {new_score:.2f} "
                f"(floor={floor:.1f}, rate={rate})"
            )

        # ── 提交所有更改 ───────────────────────────────────────────────────
        try:
            await db.commit()
            print(
                f"[intimacy-decay] Scan complete. "
                f"New decays started: {new_decay_count}, "
                f"Decays applied: {decay_applied_count}"
            )
        except Exception as exc:
            print(f"[intimacy-decay] Commit failed: {exc}")
            await db.rollback()


async def run_scheduler(interval_seconds: int = CHECK_INTERVAL):
    """
    运行亲密度衰减调度器的主循环。

    初始化数据库连接后，以固定间隔持续运行衰减扫描。
    默认每 24 小时执行一次。

    Args:
        interval_seconds: 扫描间隔时间（秒），默认为 CHECK_INTERVAL（24小时）
    """
    await init_db()
    print(
        f"[intimacy-decay] Starting intimacy decay scheduler "
        f"(interval: {interval_seconds}s)"
    )
    while True:
        try:
            await run_intimacy_decay_scan()
        except Exception as e:
            print(f"[intimacy-decay] Error during scan: {e}")
            import traceback
            traceback.print_exc()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    # 作为独立脚本运行时，启动调度器
    asyncio.run(run_scheduler())
