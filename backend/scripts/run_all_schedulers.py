"""Unified scheduler runner.

Runs both emotion_scheduler and post_scheduler concurrently
in a single async event loop to reduce SQLite write contention.

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
    )


if __name__ == "__main__":
    asyncio.run(main())
