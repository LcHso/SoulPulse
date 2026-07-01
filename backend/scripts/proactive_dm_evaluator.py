"""
主动 DM 评估器（思念触发系统）

================================================================================
功能概述
================================================================================
定时扫描所有 user-AI pair，当满足思念触发条件时，
由 LLM 生成一条引用共同记忆的主动私信，增强情感连接。

================================================================================
触发条件
================================================================================
同时满足以下条件时触发：
  1. intimacy_score >= 5.0（高亲密度用户）
  2. emotion_states.longing > 0.7（AI 的思念值较高）
  3. last_proactive_dm_at 为空或距今超过冷却时间（默认 24 小时）

================================================================================
处理流程
================================================================================
对每个满足条件的 user-AI pair：
  a. 获取该用户最近 5 条 14 天内的 fact 类型记忆
  b. 拼装 Prompt，调用 LLM 生成 DM 内容（1-3 句，中文 < 80 字）
  c. 将 DM 存入 chat_messages 表（delivered=0）
  d. 记录到 proactive_dm_logs 表
  e. 同步写入旧表 proactive_dms（兼容现有查询逻辑）
  f. 创建 Notification 推送通知
  g. 更新 interactions.last_proactive_dm_at = NOW()
  h. 更新 interactions.proactive_dm_count += 1
  i. 部分重置思念值（state.longing = 0.3）

================================================================================
冷却机制
================================================================================
默认冷却时间：24 小时。
通过 interactions.last_proactive_dm_at 字段判断，避免对同一用户过于频繁地
发送主动消息。

================================================================================
Prompt 模板
================================================================================
使用角色化的 Prompt，引导 LLM 生成自然、有记忆引用的 DM 消息。
详见 _DM_PROMPT_TEMPLATE 常量。

================================================================================
运行方式
================================================================================
从 backend 目录运行：
    python3 scripts/proactive_dm_evaluator.py

或作为模块集成到 run_all_schedulers.py 中。

作者：SoulPulse Team
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone, timedelta

# 将当前目录添加到 Python 路径，以便导入项目模块
sys.path.insert(0, ".")

from sqlalchemy import select, and_

from core.database import init_db, async_session
from models.user import User  # noqa: F401 — FK resolution
from models.ai_persona import AIPersona
from models.interaction import Interaction
from models.emotion_state import EmotionState
from models.proactive_dm import ProactiveDM
from models.proactive_dm_log import ProactiveDMLog
from models.chat_message import ChatMessage
from models.notification import Notification
from models.memory_entry import MemoryEntry

from services.aliyun_ai_service import generate_proactive_dm

# 配置日志记录
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 调度器检查间隔（秒）- 每小时运行一次
CHECK_INTERVAL = 3600  # 1 hour

# 默认冷却时间（小时）：同一 user-AI pair 两次主动 DM 之间的最短间隔
# 对应 intimacy_level_configs.proactive_cooldown_hours 的默认值
DEFAULT_COOLDOWN_HOURS = 24

# 触发条件阈值
MIN_INTIMACY_SCORE = 5.0     # 亲密度 >= 5.0
MIN_LONGING = 0.7            # 思念值 > 0.7
MEMORY_RECENT_DAYS = 14      # 获取最近 14 天内的记忆
MEMORY_LIMIT = 5             # 最多引用 5 条记忆


# ═══════════════════════════════════════════════════════════════════════════════
# DM 生成 Prompt 模板
# ═══════════════════════════════════════════════════════════════════════════════

_DM_PROMPT_TEMPLATE = """\
You are {character_name} ({character_personality_summary}).

You haven't talked to {user_name} in a while and you genuinely miss them.
Your longing level is {longing}/1.0.

Generate a SHORT, natural DM message (1-3 sentences, under 80 characters in Chinese).

Things you remember about {user_name}:
{formatted_memories}

Rules:
- Reference ONE specific memory naturally (not forced)
- Sound spontaneous, NOT like a scheduled notification
- NEVER say "as an AI" or break character
- Do NOT ask "how are you?" (too generic)
- Examples of good openers:
  "今天路过那家咖啡店，想起你说过喜欢拿铁"
  "突然想到你上次说的那件事...后来怎么样了？"
  "在听一首歌，不知道为什么会想到你"

Reply ONLY with the message text. No quotation marks, no narration.\
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 冷却时间辅助函数
# ═══════════════════════════════════════════════════════════════════════════════

def _is_cooled_down(interaction: Interaction, cooldown_hours: int) -> bool:
    """
    判断某个 user-AI pair 是否已经过了冷却时间。

    逻辑：
    - last_proactive_dm_at 为 None → 从未发送过，可以触发
    - 距今超过 cooldown_hours 小时 → 冷却结束，可以触发
    - 否则 → 仍在冷却期

    Args:
        interaction: 交互记录对象
        cooldown_hours: 冷却时间（小时）

    Returns:
        bool: True 表示已冷却（可以触发），False 表示仍在冷却期
    """
    last_dm_at = interaction.last_proactive_dm_at
    if last_dm_at is None:
        return True

    # 处理时区：确保比较一致
    now = datetime.now(timezone.utc)
    if last_dm_at.tzinfo is None:
        last_dm_at = last_dm_at.replace(tzinfo=timezone.utc)

    elapsed_hours = (now - last_dm_at).total_seconds() / 3600.0
    return elapsed_hours >= cooldown_hours


# ═══════════════════════════════════════════════════════════════════════════════
# 记忆获取与格式化
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_recent_memories(
    db, user_id: int, ai_id: int,
    days: int = MEMORY_RECENT_DAYS,
    limit: int = MEMORY_LIMIT,
) -> list[MemoryEntry]:
    """
    获取用户最近 N 天内的 fact 类型记忆。

    从 memory_entries 表中查询，按时间降序排列，取最近 limit 条。
    只取 fact 类型（具体事实：姓名、工作、爱好、偏好、日程等）。

    Args:
        db: 数据库会话
        user_id: 用户 ID
        ai_id: AI 角色 ID
        days: 查询天数范围（默认 14 天）
        limit: 返回数量上限（默认 5 条）

    Returns:
        list[MemoryEntry]: 记忆条目列表
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    # 处理 SQLite 的 naive datetime 兼容性
    cutoff_naive = cutoff.replace(tzinfo=None)

    result = await db.execute(
        select(MemoryEntry).where(
            and_(
                MemoryEntry.user_id == user_id,
                MemoryEntry.ai_id == ai_id,
                MemoryEntry.memory_type == "fact",
                MemoryEntry.created_at >= cutoff_naive,
            )
        ).order_by(MemoryEntry.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


def _format_memories_for_prompt(memories: list[MemoryEntry]) -> str:
    """
    将记忆列表格式化为 Prompt 中的文本块。

    格式：
    - "User likes coffee" (memory #1)
    - "User works as a designer" (memory #2)

    如果没有记忆则返回提示文本。

    Args:
        memories: 记忆条目列表

    Returns:
        str: 格式化后的记忆文本
    """
    if not memories:
        return "(No specific memories available — generate something generic but warm)"

    lines = []
    for i, m in enumerate(memories, 1):
        lines.append(f"- {m.content} (memory #{m.id})")
    return "\n".join(lines)


def _extract_memory_ids(memories: list[MemoryEntry]) -> list[int]:
    """
    提取记忆 ID 列表，用于写入 proactive_dm_logs.memory_refs。

    Args:
        memories: 记忆条目列表

    Returns:
        list[int]: 记忆 ID 列表
    """
    return [m.id for m in memories]


# ═══════════════════════════════════════════════════════════════════════════════
# 核心评估循环
# ═══════════════════════════════════════════════════════════════════════════════

async def run_evaluation():
    """
    执行一次完整的主动 DM 评估扫描。

    扫描流程：
    1. 查询所有满足条件的 user-AI pair（亲密度 + 思念值 + 冷却）
    2. 对每个 pair 获取记忆、调用 LLM、写入数据库
    3. 提交所有更改
    """
    print(f"[proactive-dm] Evaluation starting at {datetime.now(timezone.utc).isoformat()}")

    async with async_session() as db:
        # ── 1. 查询满足触发条件的 user-AI pair ─────────────────────────────
        # JOIN interactions + emotion_states，筛选亲密度 + 思念值
        result = await db.execute(
            select(Interaction, EmotionState).join(
                EmotionState,
                and_(
                    Interaction.user_id == EmotionState.user_id,
                    Interaction.ai_id == EmotionState.ai_id,
                ),
            ).where(
                and_(
                    Interaction.intimacy_score >= MIN_INTIMACY_SCORE,
                    EmotionState.longing > MIN_LONGING,
                )
            )
        )
        pairs = result.all()

        if not pairs:
            print("[proactive-dm] No eligible pairs found. Skipping.")
            return

        # ── 2. 预加载角色和用户信息（避免 N+1 查询）────────────────────────
        ai_ids = list({pair[0].ai_id for pair in pairs})
        user_ids = list({pair[0].user_id for pair in pairs})

        persona_res = await db.execute(
            select(AIPersona).where(AIPersona.id.in_(ai_ids))
        )
        personas = {p.id: p for p in persona_res.scalars().all()}

        user_res = await db.execute(
            select(User).where(User.id.in_(user_ids))
        )
        users = {u.id: u for u in user_res.scalars().all()}

        triggered_count = 0

        # ── 3. 遍历每个 pair，执行评估与生成 ────────────────────────────────
        for interaction, emotion_state in pairs:
            # 3a. 冷却检查
            if not _is_cooled_down(interaction, DEFAULT_COOLDOWN_HOURS):
                continue

            persona = personas.get(interaction.ai_id)
            user = users.get(interaction.user_id)
            if not persona or not user:
                continue

            # 3b. 获取该用户最近 14 天的 fact 类型记忆
            try:
                recent_memories = await _get_recent_memories(
                    db, interaction.user_id, interaction.ai_id,
                )
            except Exception as e:
                print(f"[proactive-dm] Memory fetch failed for user={interaction.user_id}: {e}")
                recent_memories = []

            # 3c. 拼装 Prompt
            # 角色性格摘要：取 personality_prompt 的前 200 字符
            personality_summary = (persona.personality_prompt or "")[:200]
            user_name = user.nickname or user.email.split("@")[0]
            formatted_memories = _format_memories_for_prompt(recent_memories)

            prompt = _DM_PROMPT_TEMPLATE.format(
                character_name=persona.name,
                character_personality_summary=personality_summary,
                user_name=user_name,
                longing=f"{emotion_state.longing:.2f}",
                formatted_memories=formatted_memories,
            )

            # 3d. 调用 LLM 生成 DM 内容
            try:
                message_text = await generate_proactive_dm(
                    persona_prompt=persona.personality_prompt,
                    system_instruction=prompt,
                    temperature=0.85,
                    max_tokens=150,
                )
            except Exception as e:
                print(
                    f"[proactive-dm] LLM generation failed for "
                    f"user={interaction.user_id} ai={interaction.ai_id}: {e}"
                )
                continue

            if not message_text or not message_text.strip():
                print(
                    f"[proactive-dm] Empty message for "
                    f"user={interaction.user_id} ai={interaction.ai_id}, skipping."
                )
                continue

            message_text = message_text.strip()

            # 3e. 写入 chat_messages（delivered=0，等待客户端拉取）
            chat_msg = ChatMessage(
                user_id=interaction.user_id,
                ai_id=interaction.ai_id,
                role="assistant",
                content=message_text,
                message_type="proactive_dm",
                event="longing",
                delivered=0,
            )
            db.add(chat_msg)
            await db.flush()  # 获取 chat_msg.id

            # 3f. 写入旧表 proactive_dms（兼容现有查询逻辑）
            dm = ProactiveDM(
                user_id=interaction.user_id,
                ai_id=interaction.ai_id,
                event="longing",
                message=message_text,
            )
            db.add(dm)

            # 3g. 写入新表 proactive_dm_logs（细粒度追踪）
            memory_ids = _extract_memory_ids(recent_memories)
            dm_log = ProactiveDMLog(
                user_id=interaction.user_id,
                character_id=interaction.ai_id,
                message_id=chat_msg.id,
                trigger_type="longing",
                memory_refs=memory_ids,
                message_text=message_text,
                user_replied=False,
            )
            db.add(dm_log)
            await db.flush()  # 获取 dm_log.id，供 Notification 使用

            # 3h. 创建推送通知
            db.add(Notification(
                user_id=interaction.user_id,
                type="proactive_dm",
                title=f"{persona.name} is thinking of you",
                body=message_text[:200],
                data_json=json.dumps({
                    "ai_id": persona.id,
                    "ai_name": persona.name,
                    "type": "longing",
                    "proactive_dm_log_id": dm_log.id,
                }, ensure_ascii=False),
            ))

            # 3i. 更新 interaction 字段
            interaction.last_proactive_dm_at = datetime.now(timezone.utc)
            interaction.proactive_dm_count = (interaction.proactive_dm_count or 0) + 1

            # 3j. 部分重置思念值（不完全清零，保留部分情感）
            emotion_state.longing = 0.3

            triggered_count += 1
            print(
                f"[proactive-dm] DM sent for user={interaction.user_id} "
                f"ai={interaction.ai_id}: {message_text[:60]}..."
            )

        # ── 4. 提交所有数据库更改 ──────────────────────────────────────────
        await db.commit()
        print(
            f"[proactive-dm] Evaluation complete. "
            f"{triggered_count} DMs triggered out of {len(pairs)} eligible pairs."
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 调度器主循环
# ═══════════════════════════════════════════════════════════════════════════════

async def run_scheduler(interval_seconds: int = CHECK_INTERVAL):
    """
    运行主动 DM 评估器的主循环。

    初始化数据库连接后，以固定间隔持续运行评估。
    每次评估完成后休眠指定时间，然后再次运行。

    Args:
        interval_seconds: 评估间隔时间（秒），默认为 CHECK_INTERVAL（1小时）

    运行方式：
        该函数会无限循环运行，直到被中断。
    """
    await init_db()
    print(
        f"[proactive-dm] Starting proactive DM evaluator "
        f"(interval: {interval_seconds}s, cooldown: {DEFAULT_COOLDOWN_HOURS}h)"
    )
    while True:
        try:
            await run_evaluation()
        except Exception as e:
            print(f"[proactive-dm] Error during evaluation: {e}")
            import traceback
            traceback.print_exc()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    # 作为独立脚本运行时，启动调度器
    asyncio.run(run_scheduler())
