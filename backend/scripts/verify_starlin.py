"""Quick verification: list all personas and StarLin's posts."""
import asyncio
import sys
sys.path.insert(0, ".")

from sqlalchemy import select
from core.database import async_session, init_db
from models.ai_persona import AIPersona
from models.post import Post


async def verify():
    await init_db()
    async with async_session() as db:
        result = await db.execute(select(AIPersona).where(AIPersona.is_active == 1))
        personas = result.scalars().all()
        print("=== All Active Personas ===")
        for p in personas:
            print(f"  ID={p.id}  name={p.name}  category={p.category}  avatar={p.avatar_url[:60] if p.avatar_url else 'N/A'}")

        print("\n=== StarLin Posts ===")
        result = await db.execute(
            select(Post).where(Post.ai_id == 5).order_by(Post.id)
        )
        posts = result.scalars().all()
        for post in posts:
            url = post.media_url[:60] if post.media_url else "EMPTY"
            print(f"  Post ID={post.id}  media={url}  caption={post.caption[:40]}...")

asyncio.run(verify())
