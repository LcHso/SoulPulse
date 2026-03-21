"""
Migration script: Fix image URLs from absolute localhost to relative paths.
Run this on the production server after pulling the latest code:
  cd backend && python3 scripts/fix_image_urls.py
"""

import asyncio
from core.database import async_session, init_db
from sqlalchemy import text


async def fix_image_urls():
    await init_db()
    async with async_session() as db:
        # Fix posts.media_url
        r = await db.execute(text(
            "UPDATE posts SET media_url = REPLACE(media_url, 'http://localhost:8001', '') "
            "WHERE media_url LIKE 'http://localhost:8001%'"
        ))
        print(f"Fixed {r.rowcount} post media URLs")

        # Fix ai_personas.avatar_url
        r = await db.execute(text(
            "UPDATE ai_personas SET avatar_url = REPLACE(avatar_url, 'http://localhost:8001', '') "
            "WHERE avatar_url LIKE 'http://localhost:8001%'"
        ))
        print(f"Fixed {r.rowcount} persona avatar URLs")

        # Fix stories.video_url
        r = await db.execute(text(
            "UPDATE stories SET video_url = REPLACE(video_url, 'http://localhost:8001', '') "
            "WHERE video_url LIKE 'http://localhost:8001%'"
        ))
        print(f"Fixed {r.rowcount} story video URLs")

        await db.commit()
        print("\nAll image URLs have been converted to relative paths.")


if __name__ == "__main__":
    asyncio.run(fix_image_urls())
