"""Generate base portraits for AI personas.

This script creates the "ID photo" for each AI character that will be used
as a face reference for all subsequent image generations.

Run from the backend directory:
    python3 scripts/generate_base_portraits.py [--force]

The generated portraits will be stored in:
- ai_personas.base_face_url: The image URL
- ai_personas.visual_prompt_tags: The visual description used
"""

from __future__ import annotations

import asyncio
import sys
import argparse

sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import init_db, async_session
from models.ai_persona import AIPersona
from services.image_gen_service import generate_base_portrait, download_to_static

# Visual Identity definitions for each persona
# These define the fixed visual traits that will be consistent across all images
PERSONA_VISUAL_TAGS = {
    "陆晨曦": {
        "gender": "female",
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
}


async def generate_portraits(force: bool = False):
    """Generate base portraits for all personas.

    Args:
        force: If True, regenerate even if base_face_url already exists.
    """
    await init_db()
    async with async_session() as db:
        result = await db.execute(
            select(AIPersona).where(AIPersona.is_active == 1)
        )
        personas = result.scalars().all()

        if not personas:
            print("[base-portrait] No active personas found.")
            return

        print(f"[base-portrait] Found {len(personas)} active personas")
        print("=" * 60)

        for persona in personas:
            print(f"\n[{persona.name}]")

            # Check if already has base face
            if persona.base_face_url and not force:
                print(f"  Already has base_face_url: {persona.base_face_url[:60]}...")
                print(f"  Use --force to regenerate")
                continue

            # Get visual tags for this persona
            visual_config = PERSONA_VISUAL_TAGS.get(persona.name)
            if not visual_config:
                print(f"  No visual config defined, skipping")
                continue

            print(f"  Gender: {visual_config['gender']}")
            print(f"  Visual tags: {visual_config['tags']}")
            print(f"  Style: {visual_config['style']}")
            print(f"  Generating base portrait...")

            try:
                # Generate the base portrait
                url = await generate_base_portrait(
                    visual_prompt_tags=visual_config["tags"],
                    gender=visual_config["gender"],
                    style=visual_config["style"],
                )

                if not url:
                    print(f"  ✗ Failed to generate")
                    continue

                print(f"  ✓ Generated: {url[:60]}...")

                # Download to local static
                local_url = await download_to_static(url, prefix=f"base_{persona.id}")

                # Update persona
                persona.base_face_url = local_url
                persona.visual_prompt_tags = visual_config["tags"]

                print(f"  ✓ Saved to: {local_url}")

                await db.commit()
                print(f"  ✓ Database updated")

            except Exception as e:
                print(f"  ✗ Error: {e}")
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