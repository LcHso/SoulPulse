"""Unified scheduler runner.

Runs emotion_scheduler, post_scheduler, proactive_dm_evaluator,
and intimacy_decay_job concurrently in a single async event loop
to reduce SQLite write contention.

Usage (from backend directory):
    python3 scripts/run_all_schedulers.py
"""

import asyncio
import sys
import logging

sys.path.insert(0, ".")

from core.database import init_db
from scripts.emotion_scheduler import run_scheduler as run_emotion_scheduler
from scripts.post_scheduler import run_scheduler as run_post_scheduler
from scripts.post_scheduler import _run_auto_approve_loop
from scripts.intimacy_decay_job import run_scheduler as run_intimacy_decay
from scripts.proactive_dm_evaluator import run_scheduler as run_proactive_dm_evaluator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("schedulers")


async def main():
    logger.info("Initializing database...")
    await init_db()
    logger.info("Starting all schedulers concurrently...")

    await asyncio.gather(
        run_emotion_scheduler(),
        run_post_scheduler(),
        _run_auto_approve_loop(),
        run_intimacy_decay(),
        run_proactive_dm_evaluator(),
    )


if __name__ == "__main__":
    asyncio.run(main())
