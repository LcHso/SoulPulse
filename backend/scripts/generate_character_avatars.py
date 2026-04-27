"""Generate semi-realistic avatar portraits for 7 AI characters.

This script generates stunning semi-realistic avatar portraits for:
- Ethan (id=1) - Photographer & coffee enthusiast based in London
- 陆晨曦 (id=2) - Gentle psychologist counselor
- 顾言深 (id=3) - Young tech CEO, cold outside but tsundere inside
- 林屿 (id=4) - Sunny college basketball captain with dimples
- 沈默白 (id=5) - Mysterious ancient book restorer
- 林星野 (id=6) - Bright idol singer with star quality
- 陆骁 (id=7) - Athletic basketball player with confident presence

Run from the backend directory:
    python3 scripts/generate_character_avatars.py
"""

from __future__ import annotations

import asyncio
import sys
import httpx
from pathlib import Path

sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import init_db, async_session
from core.config import settings
from models.ai_persona import AIPersona
from services.image_gen_service import generate_image

# Avatar output directory
AVATAR_DIR = Path(__file__).parent.parent / "static" / "avatars"

# Universal style prefix for semi-realistic look
STYLE_PREFIX = (
    "Masterpiece, best quality, 8k, semi-realistic digital art, "
    "blend of realistic proportions with stylized beauty, "
    "high-end character illustration, soft skin rendering, "
    "detailed expressive eyes, 1boy"
)

# Universal quality suffix for semi-realistic refinement
STYLE_SUFFIX = (
    "semi-realistic portrait, soft cinematic lighting, "
    "professional color grading, refined facial features, "
    "beautiful atmospheric lighting, premium character art, "
    "subtle stylization"
)

# Character definitions with semi-realistic prompts
CHARACTER_AVATARS = {
    1: {
        "name": "Ethan",
        "filename": "ethan.png",
        "prompt": (
            f"{STYLE_PREFIX}, "
            "British photographer, light brown tousled hair, hazel eyes, "
            "warm charming smile, holding vintage camera, "
            "cozy London café background, cable knit sweater, "
            "golden hour warm tones, artistic lifestyle feel, "
            f"{STYLE_SUFFIX}"
        ),
    },
    2: {
        "name": "陆晨曦",
        "filename": "luchengxi.png",
        "prompt": (
            f"{STYLE_PREFIX}, "
            "Chinese male, gentle warm counselor, soft kind eyes, "
            "warm smile, wearing comfortable cream sweater, "
            "cozy rainy-day indoor setting, warm lamp lighting, "
            "cup of coffee nearby, orange tabby cat companion, "
            "healing gentle atmosphere, "
            f"{STYLE_SUFFIX}"
        ),
    },
    3: {
        "name": "顾言深",
        "filename": "guyanshen.png",
        "prompt": (
            f"{STYLE_PREFIX}, "
            "Chinese male, young CEO, sharp handsome features, "
            "piercing cold gaze with hidden warmth, "
            "tailored dark navy suit, modern glass office with city skyline, "
            "cool blue-gray tones, sleek and sophisticated, "
            "tsundere ice prince aesthetic, "
            f"{STYLE_SUFFIX}"
        ),
    },
    4: {
        "name": "林屿",
        "filename": "linyu.png",
        "prompt": (
            f"{STYLE_PREFIX}, "
            "Chinese male, sunny basketball captain, "
            "bright genuine smile with dimples, athletic build, "
            "wearing casual sporty outfit, outdoor campus setting, "
            "golden sunlight streaming through trees, "
            "fresh energetic atmosphere, warm natural tones, "
            f"{STYLE_SUFFIX}"
        ),
    },
    5: {
        "name": "沈默白",
        "filename": "shenmobai.png",
        "prompt": (
            f"{STYLE_PREFIX}, "
            "Chinese male, mysterious book restorer, "
            "gentle deep eyes, elegant refined features, "
            "traditional-modern fusion clothing, mandarin collar shirt, "
            "atmospheric ancient library studio, muted ink-wash tones, "
            "calligraphy and old books, serene contemplative mood, "
            f"{STYLE_SUFFIX}"
        ),
    },
    6: {
        "name": "林星野",
        "filename": "linxingye.png",
        "prompt": (
            f"{STYLE_PREFIX}, "
            "Chinese male, idol singer, bright expressive starry eyes, "
            "soft warm smile, youthful face, "
            "stage/backstage setting with warm golden lights, "
            "wearing fashionable casual idol outfit, "
            "dreamy warm atmosphere, star quality charisma, "
            f"{STYLE_SUFFIX}"
        ),
    },
    7: {
        "name": "陆骁",
        "filename": "luxiao.png",
        "prompt": (
            f"{STYLE_PREFIX}, "
            "Chinese male, athletic basketball player, "
            "confident sharp gaze, strong jawline, athletic build, "
            "gym/court setting with dramatic lighting, "
            "wearing athletic wear, bold dynamic energy, "
            "warm skin tones, vibrant confident presence, "
            f"{STYLE_SUFFIX}"
        ),
    },
}


async def download_image(url: str, filepath: Path) -> bool:
    """Download image from URL to local filepath."""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f"  ERROR downloading image: {e}")
        return False


async def generate_avatar(persona_id: int, config: dict) -> bool:
    """Generate avatar for a single character."""
    name = config["name"]
    filename = config["filename"]
    prompt = config["prompt"]
    
    print(f"\n[{name}] (ID={persona_id})")
    print(f"  Generating semi-realistic avatar...")
    
    try:
        # Generate image using the project's image generation service
        urls = await generate_image(
            prompt=prompt,
            size="1024*1024",  # Square format for avatars
            n=1,
            persona_id=persona_id,  # For seed consistency
        )
        
        if not urls:
            print(f"  FAILED - no URL returned")
            return False
        
        image_url = urls[0]
        print(f"  Generated: {image_url[:80]}...")
        
        # Ensure avatar directory exists
        AVATAR_DIR.mkdir(parents=True, exist_ok=True)
        
        # Download to local static/avatars directory
        filepath = AVATAR_DIR / filename
        success = await download_image(image_url, filepath)
        
        if success:
            print(f"  Saved: {filepath}")
            return True
        else:
            print(f"  FAILED to download image")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


async def update_database_avatar_url(persona_id: int, avatar_path: str) -> bool:
    """Update the avatar_url in database for the persona."""
    try:
        async with async_session() as db:
            result = await db.execute(
                select(AIPersona).where(AIPersona.id == persona_id)
            )
            persona = result.scalar_one_or_none()
            
            if persona:
                persona.avatar_url = avatar_path
                await db.commit()
                print(f"  Database updated: avatar_url = {avatar_path}")
                return True
            else:
                print(f"  WARNING: Persona ID {persona_id} not found in database")
                return False
    except Exception as e:
        print(f"  ERROR updating database: {e}")
        return False


async def main():
    print("=" * 70)
    print("SoulPulse Character Avatar Generator (Semi-Realistic Style)")
    print("=" * 70)
    print(f"\nModel: {settings.DASHSCOPE_IMAGE_MODEL}")
    print(f"Target directory: {AVATAR_DIR}")
    print("\nGenerating semi-realistic avatars for 7 characters:")
    print("  - Ethan (id=1) - British photographer")
    print("  - 陆晨曦 (id=2) - Gentle counselor")
    print("  - 顾言深 (id=3) - Cold CEO")
    print("  - 林屿 (id=4) - Sunny basketball captain")
    print("  - 沈默白 (id=5) - Mysterious book restorer")
    print("  - 林星野 (id=6) - Idol singer")
    print("  - 陆骁 (id=7) - Athletic basketball player")
    print("=" * 70)
    
    # Initialize database
    await init_db()
    
    success_count = 0
    
    for persona_id, config in CHARACTER_AVATARS.items():
        success = await generate_avatar(persona_id, config)
        
        if success:
            # Update database with new avatar path
            avatar_path = f"/static/avatars/{config['filename']}"
            await update_database_avatar_url(persona_id, avatar_path)
            success_count += 1
        
        # Small delay between generations to avoid rate limiting
        await asyncio.sleep(2)
    
    print("\n" + "=" * 70)
    print(f"Generation complete: {success_count}/{len(CHARACTER_AVATARS)} avatars generated")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
