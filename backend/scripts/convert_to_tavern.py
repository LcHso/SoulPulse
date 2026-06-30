"""
Convert all SoulPulse character markdown files to SillyTavern V2 card format.

This script:
1. Reads all character .md files from the project root
2. Converts each to SillyTavern V2 card format
3. Saves JSON output to backend/static/cards/{character_name}_card.json
4. Updates the database: sets tavern_card_json on each matching AIPersona record

Usage:
    cd backend && python3 -m scripts.convert_to_tavern
    cd backend && python3 -m scripts.convert_to_tavern --force  # overwrite existing cards
"""

import asyncio
import argparse
import json
import os
import sys
from pathlib import Path

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.character_card_service import convert_markdown_to_card, card_to_json_string
from core.database import async_session, init_db
from models.ai_persona import AIPersona
from sqlalchemy import select


# Character markdown files and their corresponding persona names
CHARACTER_FILES = {
    "starlin.md": "林星野",
    "luxiao.md": "陆骁",
    "jiyechen.md": "季夜尘",
    "guyanshen.md": "顾言深",
    "luchenxi.md": "陆晨曦",
    "shenmobai.md": "沈默白",
    "fujichuan.md": "傅霁川",
    "helianye.md": "赫连烨",
    "jiangyubai.md": "江屿白",
    "peiluo.md": "裴洛",
    "wenshixu.md": "温时序",
}

# Project root (one level up from backend/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CARDS_DIR = Path(__file__).resolve().parent.parent / "static" / "cards"


def convert_all_characters(force: bool = False) -> dict:
    """
    Convert all character markdown files to SillyTavern V2 card JSON.
    
    Args:
        force: If True, overwrite existing card JSON files.
    
    Returns:
        dict mapping persona_name -> card_json_string for successfully converted characters.
    """
    # Ensure output directory exists
    CARDS_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    skipped = []
    errors = []

    for md_filename, persona_name in CHARACTER_FILES.items():
        md_path = PROJECT_ROOT / md_filename
        # Output filename uses the md stem (e.g., starlin_card.json)
        card_filename = f"{md_path.stem}_card.json"
        card_path = CARDS_DIR / card_filename

        # Check if file exists
        if not md_path.exists():
            errors.append((persona_name, f"Markdown file not found: {md_path}"))
            continue

        # Skip if already exists and not forcing
        if card_path.exists() and not force:
            skipped.append(persona_name)
            # Still load the existing JSON for DB update
            with open(card_path, 'r', encoding='utf-8') as f:
                results[persona_name] = f.read()
            continue

        try:
            # Convert markdown to card
            card = convert_markdown_to_card(str(md_path))
            card_json_str = card_to_json_string(card)

            # Save to file
            with open(card_path, 'w', encoding='utf-8') as f:
                f.write(card_json_str)

            results[persona_name] = card_json_str
            print(f"  [OK] {persona_name} ({md_filename}) -> {card_filename}")

        except Exception as e:
            errors.append((persona_name, str(e)))
            print(f"  [ERROR] {persona_name} ({md_filename}): {e}")

    return results, skipped, errors


async def update_database(card_data: dict):
    """
    Update the tavern_card_json field for each persona in the database.
    
    Args:
        card_data: dict mapping persona_name -> card_json_string
    """
    await init_db()
    updated = 0
    not_found = []

    async with async_session() as db:
        for persona_name, json_str in card_data.items():
            result = await db.execute(
                select(AIPersona).where(AIPersona.name == persona_name)
            )
            persona = result.scalar_one_or_none()

            if persona:
                persona.tavern_card_json = json_str
                updated += 1
            else:
                not_found.append(persona_name)

        await db.commit()

    return updated, not_found


async def main():
    parser = argparse.ArgumentParser(
        description="Convert SoulPulse character markdown files to SillyTavern V2 card format"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing card JSON files"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("SoulPulse -> SillyTavern V2 Card Converter")
    print("=" * 60)
    print(f"\nProject root: {PROJECT_ROOT}")
    print(f"Output dir:   {CARDS_DIR}")
    print(f"Force mode:   {args.force}")
    print(f"\nConverting {len(CHARACTER_FILES)} characters...\n")

    # Step 1: Convert markdown files to card JSON
    card_data, skipped, errors = convert_all_characters(force=args.force)

    # Step 2: Update database
    print("\nUpdating database...")
    try:
        updated, not_found = await update_database(card_data)
        print(f"  Database updated: {updated} personas")
        if not_found:
            print(f"  Not in DB (JSON saved only): {', '.join(not_found)}")
    except Exception as e:
        print(f"  Database update failed: {e}")
        print("  (Card JSON files were still saved successfully)")
        updated = 0
        not_found = list(card_data.keys())

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Converted:    {len(card_data) - len(skipped)}")
    print(f"  Skipped:      {len(skipped)} (already exist, use --force to overwrite)")
    print(f"  Errors:       {len(errors)}")
    print(f"  DB updated:   {updated}")
    if errors:
        print("\nErrors:")
        for name, err in errors:
            print(f"  - {name}: {err}")
    if skipped:
        print(f"\nSkipped (existing): {', '.join(skipped)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
