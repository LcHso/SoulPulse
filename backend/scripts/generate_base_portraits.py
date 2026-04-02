"""Regenerate base portraits + avatars for all AI personas using latest model.

This script:
1. Auto-adds missing columns (base_face_url, visual_prompt_tags, visual_description)
2. Generates a high-quality base portrait for each persona
3. Downloads the image to local static storage
4. Updates both base_face_url and avatar_url in the database

Run from the backend directory:
    python3 scripts/generate_base_portraits.py [--force]
"""

from __future__ import annotations

import asyncio
import sys
import argparse

sys.path.insert(0, ".")

from sqlalchemy import select, text

from core.database import init_db, async_session
from models.ai_persona import AIPersona
from services.image_gen_service import generate_base_portrait, download_to_static

# Visual Identity definitions for each persona
PERSONA_VISUAL_TAGS = {
    "Ethan": {
        "gender": "male",
        "tags": "light brown tousled hair, hazel eyes, warm charming smile, defined cheekbones, clean shaven, youthful face",
        "style": "photorealistic, warm golden hour aesthetic",
    },
    "陆晨曦": {
        "gender": "male",
        "tags": "long brown wavy hair, gentle eyes, warm smile, soft features, natural makeup",
        "style": "photorealistic, soft dreamy aesthetic",
    },
    "顾言深": {
        "gender": "male",
        "tags": "short black hair, sharp jawline, deep dark eyes, serious expression, clean shaven",
        "style": "photorealistic, minimalist dark aesthetic",
    },
    "林屿": {
        "gender": "male",
        "tags": "short sporty hair, bright energetic eyes, warm smile, athletic build, youthful appearance",
        "style": "photorealistic, bright youthful aesthetic",
    },
    "沈默白": {
        "gender": "male",
        "tags": "slightly long messy black hair, mysterious dark eyes, pale complexion, elegant features",
        "style": "photorealistic, traditional elegant aesthetic",
    },
    "林星野": {
        "gender": "male",
        "tags": "soft textured black hair, bright expressive eyes, gentle dimple smile, slim narrow face with sharp chin, fair skin, 21 year old Chinese male idol, slim build, wearing casual white hoodie with star print, warm natural lighting",
        "style": "photorealistic, Chinese idol aesthetic, warm soft lighting, clean and natural vibe",
    },
    "陆骁": {
        "gender": "male",
        "tags": "buzz cut, sharp jawline, tanned skin, broad shoulders, defined abs, athletic muscular build, intense gaze",
        "style": "photorealistic, gym aesthetic, cinematic low-key lighting, grey cotton fabric focus, low-rise shorts, muscular contours",
        "negative": "feminine, soft, skinny, long hair, loose clothing, cartoon, anime, blurry",
    },
}


async def ensure_columns(db):
    """Add missing columns to ai_personas table if they don't exist."""
    # Check existing columns
    result = await db.execute(text("PRAGMA table_info(ai_personas)"))
    existing = {row[1] for row in result.fetchall()}

    migrations = {
        "base_face_url": "ALTER TABLE ai_personas ADD COLUMN base_face_url VARCHAR(500)",
        "visual_prompt_tags": "ALTER TABLE ai_personas ADD COLUMN visual_prompt_tags TEXT",
        "visual_description": "ALTER TABLE ai_personas ADD COLUMN visual_description TEXT",
    }

    for col, sql in migrations.items():
        if col not in existing:
            print(f"  Adding missing column: {col}")
            await db.execute(text(sql))
            await db.commit()


async def generate_portraits(force: bool = False):
    await init_db()
    async with async_session() as db:
        # Auto-migrate missing columns
        await ensure_columns(db)

        result = await db.execute(
            select(AIPersona).where(AIPersona.is_active == 1)
        )
        personas = result.scalars().all()

        if not personas:
            print("[base-portrait] No active personas found.")
            return

        print(f"[base-portrait] Found {len(personas)} active personas")
        print(f"[base-portrait] Model: {__import__('core.config', fromlist=['settings']).settings.DASHSCOPE_IMAGE_MODEL}")
        print("=" * 60)

        for persona in personas:
            print(f"\n[{persona.name}] (ID={persona.id})")

            if persona.base_face_url and not force:
                print(f"  Already has base_face_url, use --force to regenerate")
                continue

            visual_config = PERSONA_VISUAL_TAGS.get(persona.name)
            if not visual_config:
                print(f"  No visual config defined for '{persona.name}', skipping")
                continue

            print(f"  Gender: {visual_config['gender']}")
            print(f"  Tags: {visual_config['tags']}")
            print(f"  Generating...")

            try:
                url = await generate_base_portrait(
                    visual_prompt_tags=visual_config["tags"],
                    gender=visual_config["gender"],
                    style=visual_config["style"],
                )

                if not url:
                    print(f"  FAILED - no URL returned")
                    continue

                print(f"  Generated: {url[:80]}...")

                local_url = await download_to_static(url, prefix=f"base_{persona.id}")

                persona.base_face_url = local_url
                persona.avatar_url = local_url
                persona.visual_prompt_tags = visual_config["tags"]

                await db.commit()
                print(f"  Saved: {local_url}")
                print(f"  avatar_url updated")

            except Exception as e:
                print(f"  ERROR: {e}")
                continue

        print("\n" + "=" * 60)
        print("[base-portrait] Done!")


async def main():
    parser = argparse.ArgumentParser(description="Generate base portraits for AI personas")
    parser.add_argument("--force", action="store_true", help="Regenerate existing portraits")
    args = parser.parse_args()
    await generate_portraits(force=args.force)


if __name__ == "__main__":
    asyncio.run(main())
