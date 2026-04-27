"""Generate post and story images for 林星野 (Linxingye, AI ID=6).

Creates 3 post images + 1 story image using DashScope wanx API,
downloads them to backend/static/ with correct filenames.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import httpx
from services.image_gen_service import generate_image

PERSONA_ID = 6
VISUAL_BASE = (
    "young Asian male idol singer, soft textured black hair, bright expressive deer-like eyes, "
    "dimpled smile, slim narrow face, Chinese idol aesthetic, warm natural vibe"
)

# 3 post prompts + 1 story prompt
IMAGE_SPECS = [
    {
        "filename": "static/posts/linxingye_1.png",
        "size": "720*1280",
        "prompt": (
            f"{VISUAL_BASE}, performing on concert stage, dynamic dance pose, "
            "colorful stage lights, neon blue and purple spotlights, energetic atmosphere, "
            "wearing stylish stage outfit with sequins, crowd silhouettes in background, "
            "professional concert photography"
        ),
    },
    {
        "filename": "static/posts/linxingye_2.png",
        "size": "1024*1024",
        "prompt": (
            f"{VISUAL_BASE}, candid backstage moment, sitting on makeup chair, "
            "wearing casual white hoodie, holding a strawberry milk drink, "
            "soft warm lighting, mirror with lightbulbs in background, relaxed happy expression, "
            "behind-the-scenes idol life photography"
        ),
    },
    {
        "filename": "static/posts/linxingye_3.png",
        "size": "1024*1024",
        "prompt": (
            f"{VISUAL_BASE}, in professional recording studio, wearing headphones around neck, "
            "standing near microphone, warm studio lighting, acoustic panels on walls, "
            "holding lyric notebook, thoughtful gentle expression, music creation moment"
        ),
    },
    {
        "filename": "static/stories/linxingye.png",
        "size": "720*1280",
        "prompt": (
            f"{VISUAL_BASE}, close-up selfie style portrait, playful wink expression, "
            "practice room mirror background, slightly sweaty after dance practice, "
            "wearing black tank top, holding teddy bear plushie, soft natural lighting, "
            "intimate vlog-style photo, looking directly at camera"
        ),
    },
]

BASE_DIR = Path(__file__).parent.parent


async def download_image(url: str, dest: Path):
    """Download image from URL to local path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
    print(f"  Saved: {dest} ({dest.stat().st_size} bytes)")


async def main():
    for i, spec in enumerate(IMAGE_SPECS):
        label = spec["filename"]
        print(f"\n[{i+1}/{len(IMAGE_SPECS)}] Generating: {label}")
        print(f"  Prompt: {spec['prompt'][:100]}...")

        try:
            urls = await generate_image(
                prompt=spec["prompt"],
                size=spec["size"],
                n=1,
                persona_id=PERSONA_ID,
            )
            if not urls:
                print("  ERROR: No URLs returned")
                continue

            remote_url = urls[0]
            print(f"  Remote URL: {remote_url[:100]}...")

            dest = BASE_DIR / spec["filename"]
            await download_image(remote_url, dest)

        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
