"""Regenerate base portraits + avatars for all AI personas.

Dispatches to the configured image backend:
  * IMAGE_BACKEND=nai       -> delegates to scripts.generate_nai_portraits
  * IMAGE_BACKEND=dashscope -> uses the legacy DashScope generator

This script:
1. Auto-adds missing columns (base_face_url, visual_prompt_tags, visual_description)
2. Generates a high-quality base portrait for each persona
3. Persists the image to local static storage
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

from core.config import settings
from core.database import init_db, async_session
from models.ai_persona import AIPersona
from services.image_gen_service import generate_base_portrait, download_to_static

# Import centralized NAI visual tags from seed_personas
from scripts.seed_personas import PERSONA_VISUAL_TAGS


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
                    style=visual_config.get("style", "anime illustration"),
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
    parser.add_argument("--character", type=str, default=None,
                        help="(NAI backend only) Generate for a single character name")
    parser.add_argument("--dry-run", action="store_true",
                        help="(NAI backend only) Print what would be generated without calling the API")
    args = parser.parse_args()

    backend = (settings.IMAGE_BACKEND or "").lower()
    if backend == "nai":
        # Delegate to the dedicated NAI script for consistency.
        from scripts.generate_nai_portraits import run as run_nai
        print(f"[base-portrait] IMAGE_BACKEND=nai -> delegating to generate_nai_portraits")
        exit_code = await run_nai(
            character=args.character,
            force=args.force,
            dry_run=args.dry_run,
        )
        if exit_code:
            sys.exit(exit_code)
        return

    # Legacy DashScope path
    print(f"[base-portrait] IMAGE_BACKEND={backend or 'dashscope'} -> using DashScope path")
    await generate_portraits(force=args.force)


if __name__ == "__main__":
    asyncio.run(main())
