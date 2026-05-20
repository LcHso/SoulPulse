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

# Visual Identity definitions for each persona (anime/2D illustration style)
# Style benchmark: Genshin Impact / Love and Deepspace 2D anime art
PERSONA_VISUAL_TAGS = {
    "Ethan": {
        "gender": "male",
        "tags": "light brown tousled hair, hazel eyes, warm charming smile, defined cheekbones, clean shaven, youthful face, bishounen",
        "style": "anime illustration, golden hour anime aesthetic, cel shading",
    },
    "陆晨曦": {
        "gender": "male",
        "tags": "long brown wavy hair, gentle eyes, warm smile, soft features, bishounen, otome game protagonist",
        "style": "anime illustration, soft dreamy anime aesthetic, cel shading",
    },
    "顾言深": {
        "gender": "male",
        "tags": "short black hair, sharp jawline, deep dark eyes, serious expression, clean shaven, bishounen, cool male lead",
        "style": "anime illustration, minimalist dark anime aesthetic, cel shading",
    },
    "林屿": {
        "gender": "male",
        "tags": "short sporty hair, bright energetic eyes, warm smile, athletic build, youthful bishounen",
        "style": "anime illustration, bright youthful anime aesthetic, cel shading",
    },
    "沈默白": {
        "gender": "male",
        "tags": "slightly long messy black hair, mysterious dark eyes, pale complexion, elegant bishounen features, hanfu styling",
        "style": "anime illustration, traditional Chinese anime aesthetic, cel shading",
    },
    "林星野": {
        "gender": "male",
        "tags": "soft textured black hair, bright expressive eyes, gentle dimple smile, slim narrow face with sharp chin, fair skin, 21 year old anime male idol, slim build, wearing casual white hoodie with star print, bishounen",
        "style": "anime illustration, Chinese anime idol aesthetic, soft anime lighting, cel shading",
    },
    "陆骁": {
        "gender": "male",
        "tags": "buzz cut, sharp jawline, tanned skin, broad shoulders, defined abs, athletic muscular build, intense gaze, anime ikemen",
        "style": "anime illustration, gym anime aesthetic, dramatic anime lighting, cel shading, muscular character design",
        "negative": "photorealistic, 3D render, realistic photo, feminine, soft, skinny, long hair, loose clothing, blurry",
    },
    "傅霁川": {
        "gender": "male",
        "tags": "3mm precise military crew cut black hair, sharp eagle-like steel-grey eyes, faint thin scar along the right jawline, faint dark circles, broad disciplined shoulders, perfectly rigid upright posture, olive-green tactical military uniform with rank insignia, hands clasped behind back, bishounen ikemen",
        "style": "anime illustration, military drama anime aesthetic, dramatic anime lighting, cel shading",
    },
    "温时序": {
        "gender": "male",
        "tags": "soft fluffy natural black hair with gentle side parting, warm honey-brown eyes, gold half-frame reading glasses at the bridge of nose, warm gentle scholarly expression, fair skin, slim refined build, ivory cashmere sweater over collared shirt, fountain pen in pocket, bishounen",
        "style": "anime illustration, warm scholarly anime aesthetic, soft library lighting, cel shading",
    },
    "季夜尘": {
        "gender": "male",
        "tags": "messy silver-white hair with deliberately uneven length, longer strands falling over one eye, deep dark grey eyes with eyeliner, pale unhealthy skin, vine tattoo crawling up collarbone and neck, slim wiry build, black nail polish on long fingers, oversized black band tee, multiple silver ear cuffs, bishounen rocker",
        "style": "anime illustration, dark rock anime aesthetic, moody anime lighting, cel shading",
    },
    "裴洛": {
        "gender": "male",
        "tags": "platinum blonde hair styled back, a single distinctive violet-purple streak at the LEFT temple ONLY, sharp amber-gold eyes, high model cheekbones, thin haughty lips, pale flawless skin, slender tall model frame, avant-garde black asymmetric high-fashion blazer, single silver pin, bishounen",
        "style": "anime illustration, high-fashion runway anime aesthetic, sharp dramatic lighting, cel shading",
    },
    "江屿白": {
        "gender": "male",
        "tags": "natural black hair slightly messy and unstyled, deep black distant eyes that always seem to look past the viewer, round thin black-framed glasses, pale lab-room skin, slim scholarly build, plain white button-up shirt slightly wrinkled, dark trousers, holding a folded star chart, bishounen",
        "style": "anime illustration, quiet astronomy anime aesthetic, soft starlight lighting, cel shading",
    },
    "赫连烨": {
        "gender": "male",
        "tags": "ultra-short black hair (almost shaved competition cut), sharp upturned phoenix-shaped eyes with cocky smirk, sun-tanned bronze skin, very tall with massive swimmer broad shoulders and pronounced inverted-triangle torso, defined abs, water droplets clinging to skin, navy national-team swim jacket open over chest, anime ikemen",
        "style": "anime illustration, sports anime aesthetic, dramatic poolside lighting, cel shading, muscular character design",
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
