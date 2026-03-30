"""
Seed script to populate posts, stories, and avatar URLs for all personas.
Uses locally generated static images served by FastAPI.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from core.database import async_session, init_db
from models.ai_persona import AIPersona
from models.post import Post
from models.story import Story
from sqlalchemy import select, delete


# Base URL for static files - use relative paths so they work in any environment
STATIC_BASE = "/static"

# Map persona name -> slug used in filenames
PERSONA_SLUGS = {
    "陆晨曦": "luchengxi",
    "顾言深": "guyanshen",
    "林屿": "linyu",
    "沈默白": "shenmobai",
    "Ethan": "ethan",  # legacy persona, no images yet
}

# Visual descriptions for consistent AI image generation
# Each persona has fixed visual traits for character consistency
VISUAL_DESCRIPTIONS = {
    "陆晨曦": "young Asian female, long brown wavy hair, gentle smile, casual cozy fashion, warm aesthetic",
    "顾言深": "young Asian male, short black hair, serious expression, minimalist dark style, professional look",
    "林屿": "young Asian male, short sporty hair, energetic smile, athletic wear, bright youthful vibe",
    "沈默白": "young Asian male, slightly long messy hair, mysterious calm expression, traditional elegant style",
}

# Post content per persona: list of (caption, is_close_friend)
POST_DATA = {
    "陆晨曦": [
        ("下雨天窝在家里煮咖啡看书，年糕趴在腿上打呼噜...这大概就是我最喜欢的周末了吧 ☕🐱", False),
        ("最近在读阿德勒的《被讨厌的勇气》，感觉每一页都在和自己对话。推荐给最近有点迷茫的你 📖", False),
        ("年糕今天又闯祸了...把毛线球拆得满地都是。但看到这个小眼神，我真的生不起气来 🧶😾", False),
    ],
    "顾言深": [
        ("凌晨三点的城市，只有代码和我还醒着。新项目上线倒计时。", False),
        ("Alpha今天跑了三公里才肯回来。这狗的体力比我好。", False),
        ("有人问我为什么办公桌上放甜甜圈...不关你们的事。", True),  # close friend only
    ],
    "林屿": [
        ("今天三分球10投8中！！！队友都说我开挂了哈哈哈 太爽了🏀🔥", False),
        ("想妈妈做的红烧肉了...食堂的怎么做都不是那个味道😭 有没有人教教我", False),
        ("夕阳下的球场，是属于我们的青春没错了💪 兄弟们下学期继续冲！", False),
    ],
    "沈默白": [
        ("修复一本明代古籍，纸张脆如蝉翼。每一笔都要屏住呼吸，但这种专注让人安宁。", False),
        ("墨今天难得晒太阳，趴在窗台上看院子里的茶花开了。岁月静好大概就是这样。", False),
        ("夜深了，泡一壶老白茶，临一帖颜真卿。笔墨之间，万物皆静。", False),
    ],
}

# Story content per persona: (caption,)
STORY_DATA = {
    "陆晨曦": "窗外又下雨了，给你们看看我最爱的雨景 🌧️",
    "顾言深": "加班到现在...这城市的夜景算是补偿吧",
    "林屿": "练完球！鞋都湿透了但是好开心！💪",
    "沈默白": "深夜练字，心如止水",
}


async def seed_content(force_recreate: bool = False):
    """Seed posts, stories, and update avatar URLs."""
    await init_db()
    async with async_session() as db:
        # Load all personas
        result = await db.execute(select(AIPersona))
        personas = {p.name: p for p in result.scalars().all()}

        if not personas:
            print("[seed-content] No personas found! Run seed_personas.py first.")
            return

        if force_recreate:
            await db.execute(delete(Post))
            await db.execute(delete(Story))
            await db.commit()
            print("[seed-content] Deleted all existing posts and stories")

        # ── Update avatar URLs and visual descriptions ─────────────────────────────────
        for name, persona in personas.items():
            slug = PERSONA_SLUGS.get(name)
            if slug and slug != "ethan":
                persona.avatar_url = f"{STATIC_BASE}/avatars/{slug}.png"
                print(f"[seed-content] Updated avatar: {name} -> {persona.avatar_url}")
            # Set visual description for consistent image generation
            if name in VISUAL_DESCRIPTIONS:
                persona.visual_description = VISUAL_DESCRIPTIONS[name]
                print(f"[seed-content] Set visual description for {name}")

        await db.commit()

        # ── Check if posts already exist ───────────────────────
        existing_posts = await db.execute(select(Post).limit(1))
        if existing_posts.scalar_one_or_none() and not force_recreate:
            print("[seed-content] Posts already exist, skipping. Use --force to recreate.")
            return

        # ── Create posts ───────────────────────────────────────
        now = datetime.now(timezone.utc)
        post_count = 0
        for name, post_list in POST_DATA.items():
            persona = personas.get(name)
            if not persona:
                print(f"[seed-content] Persona '{name}' not found, skipping posts")
                continue

            slug = PERSONA_SLUGS[name]
            for i, (caption, is_cf) in enumerate(post_list):
                post = Post(
                    ai_id=persona.id,
                    media_url=f"{STATIC_BASE}/posts/{slug}_{i+1}.png",
                    caption=caption,
                    like_count=__import__("random").randint(12, 88),
                    is_close_friend=is_cf,
                )
                # Stagger creation times so feed looks natural
                post.created_at = now - timedelta(hours=(len(post_list) - i) * 8 + __import__("random").randint(0, 4))
                db.add(post)
                post_count += 1

        await db.commit()
        print(f"[seed-content] Created {post_count} posts")

        # ── Create stories (expire in 24h) ─────────────────────
        story_count = 0
        for name, caption in STORY_DATA.items():
            persona = personas.get(name)
            if not persona:
                continue

            slug = PERSONA_SLUGS[name]
            story = Story(
                ai_id=persona.id,
                video_url=f"{STATIC_BASE}/stories/{slug}.png",
                caption=caption,
                expires_at=now + timedelta(hours=24),
            )
            story.created_at = now - timedelta(hours=__import__("random").randint(1, 6))
            db.add(story)
            story_count += 1

        await db.commit()
        print(f"[seed-content] Created {story_count} stories")
        print("\n[seed-content] Done!")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    if force:
        print("[seed-content] Force recreate mode!")
    asyncio.run(seed_content(force_recreate=force))
