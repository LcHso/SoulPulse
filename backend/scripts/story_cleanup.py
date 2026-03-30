"""Story cleanup scheduler.

Removes expired stories from the database to prevent accumulation.
Run periodically (hourly recommended) via systemd or cron.

Run from the backend directory:
    python3 scripts/story_cleanup.py
"""

from __future__ import annotations

import asyncio
import sys
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")

from sqlalchemy import delete, select, func

from core.database import init_db, async_session
from models.story import Story

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Delete stories that expired more than this many hours ago
# This gives a grace period for any in-flight requests
GRACE_PERIOD_HOURS = 1


async def cleanup_expired_stories():
    """Delete stories that have expired (plus grace period)."""
    await init_db()
    async with async_session() as db:
        # Count stories to delete
        cutoff = datetime.now(timezone.utc) - timedelta(hours=GRACE_PERIOD_HOURS)
        
        # Handle naive datetime in database
        cutoff_naive = cutoff.replace(tzinfo=None)
        
        count_result = await db.execute(
            select(func.count(Story.id)).where(Story.expires_at < cutoff_naive)
        )
        count = count_result.scalar() or 0
        
        if count == 0:
            print(f"[story-cleanup] No expired stories to delete.")
            return 0
        
        # Delete expired stories
        await db.execute(delete(Story).where(Story.expires_at < cutoff_naive))
        await db.commit()
        
        print(f"[story-cleanup] Deleted {count} expired stories (expired before {cutoff_naive}).")
        return count


async def main():
    """Run cleanup once."""
    print(f"[story-cleanup] Starting at {datetime.now(timezone.utc).isoformat()}")
    deleted = await cleanup_expired_stories()
    print(f"[story-cleanup] Complete. Deleted {deleted} stories.")


if __name__ == "__main__":
    asyncio.run(main())