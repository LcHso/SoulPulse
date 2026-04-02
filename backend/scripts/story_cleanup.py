"""
故事清理调度器 - SoulPulse 数据库维护模块

功能概述：
    该脚本负责定期清理数据库中已过期的 Story（故事）记录。
    Story 在创建时设置了 expires_at 字段（默认24小时后过期），
    此脚本会删除那些已过期超过宽限期时间的故事记录。

    这是一个数据库维护脚本，用于防止 Story 数据无限累积，
    保持数据库清洁和性能。

调度逻辑：
    - 建议运行频率：每小时执行一次
    - 宽限期：1小时（GRACE_PERIOD_HOURS = 1）
    - 清理规则：删除 expires_at 超过当前时间减去宽限期的故事

触发条件：
    手动执行或通过系统调度器（systemd/cron）定期运行

为什么需要宽限期：
    宽限期（1小时）是为了处理时间边界情况：
    - 数据库时间可能与时区处理有细微偏差
    - 某些请求可能正在处理刚过期的故事
    - 给予用户一个缓冲时间，避免刚过期就立即消失

运行方式：
    从 backend 目录运行：
        python3 scripts/story_cleanup.py

    通过 systemd 定时运行（推荐）：
        在 systemd service 中配置定时执行

    通过 cron 定时运行：
        0 * * * * cd /path/to/backend && python3 scripts/story_cleanup.py

数据影响：
    - 删除操作不可逆，但只删除已过期的故事
    - Story 过期本是正常行为，此脚本只是清理数据库记录

作者：SoulPulse Team
"""

from __future__ import annotations

import asyncio
import sys
import logging
from datetime import datetime, timezone, timedelta

# 将当前目录添加到 Python 路径，以便导入项目模块
sys.path.insert(0, ".")

from sqlalchemy import delete, select, func

from core.database import init_db, async_session
from models.story import Story

# 配置日志记录
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 宽限期配置（小时）
# 删除过期时间超过此值的故事，给予一个缓冲时间处理正在进行的请求
GRACE_PERIOD_HOURS = 1


async def cleanup_expired_stories():
    """
    清理已过期的故事记录。

    处理流程：
        1. 计算清理截止时间（当前时间 - 宽限期）
        2. 统计待删除的故事数量
        3. 如果没有过期故事，直接返回
        4. 执行删除操作
        5. 提交更改并输出统计信息

    参数：
        无参数

    返回：
        int: 删除的故事数量

    注意：
        - 数据库中的 expires_at 可能是 naive datetime（无时区信息）
        - 需要将截止时间转换为 naive datetime 进行比较
    """
    await init_db()
    async with async_session() as db:
        # 步骤1：计算清理截止时间
        # 当前时间减去宽限期，得到故事应该被删除的时间点
        cutoff = datetime.now(timezone.utc) - timedelta(hours=GRACE_PERIOD_HOURS)

        # 处理数据库中的 naive datetime（无时区信息）
        # SQLite 等数据库可能不存储时区信息，需要统一格式
        cutoff_naive = cutoff.replace(tzinfo=None)

        # 步骤2：统计待删除的故事数量
        count_result = await db.execute(
            select(func.count(Story.id)).where(Story.expires_at < cutoff_naive)
        )
        count = count_result.scalar() or 0

        # 步骤3：如果没有过期故事，直接返回
        if count == 0:
            print(f"[story-cleanup] No expired stories to delete.")
            return 0

        # 步骤4：执行删除操作
        await db.execute(delete(Story).where(Story.expires_at < cutoff_naive))
        await db.commit()

        # 步骤5：输出清理结果
        print(f"[story-cleanup] Deleted {count} expired stories (expired before {cutoff_naive}).")
        return count


async def main():
    """
    运行故事清理任务的主入口函数。

    执行一次清理操作并输出完成信息。
    此函数不循环运行，适合通过外部调度器定时触发。

    处理流程：
        1. 输出开始时间
        2. 执行清理操作
        3. 输出完成统计
    """
    print(f"[story-cleanup] Starting at {datetime.now(timezone.utc).isoformat()}")
    deleted = await cleanup_expired_stories()
    print(f"[story-cleanup] Complete. Deleted {deleted} stories.")


if __name__ == "__main__":
    # 作为独立脚本运行时，执行一次性清理
    asyncio.run(main())