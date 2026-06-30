"""
Generate a single character's portrait and three-view for review.

Usage:
    python3 -m scripts.generate_single_character --character "林星野" --type portrait
    python3 -m scripts.generate_single_character --character "林星野" --type three_view
    python3 -m scripts.generate_single_character --character "林星野" --type all

Saves output to backend/static/review/{character_slug}_{type}_{timestamp}.png
"""
import sys
import os
import asyncio
import argparse
import time
import hashlib

# Ensure imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.image_gen_service import generate_image, ENFORCED_NEGATIVE_PROMPT
from core.config import settings

# Import WAN27 prompts
from scripts.seed_personas import WAN27_PROMPTS

NAME_TO_SLUG = {
    "林星野": "linxingye",
    "陆骁": "luxiao",
    "季夜尘": "jiyechen",
    "顾言深": "guyanshen",
    "陆晨曦": "luchenxi",
    "沈默白": "shenmobai",
    "傅霁川": "fujichuan",
    "赫连烨": "helianye",
    "江屿白": "jiangyubai",
    "裴洛": "peiluo",
    "温时序": "wenshixu",
}


def _get_seed(name: str) -> int:
    return int(hashlib.md5(f"wan27_{name}".encode()).hexdigest()[:8], 16) % 2147483647


async def generate_character(name: str, gen_type: str = "all"):
    """Generate portrait and/or three-view for a character."""
    if name not in WAN27_PROMPTS:
        print(f"Error: Unknown character '{name}'")
        print(f"Available: {', '.join(WAN27_PROMPTS.keys())}")
        return

    slug = NAME_TO_SLUG[name]
    prompts = WAN27_PROMPTS[name]
    seed = _get_seed(name)
    timestamp = int(time.time())

    # Ensure output dir exists
    review_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "review")
    os.makedirs(review_dir, exist_ok=True)

    results = []

    if gen_type in ("portrait", "all"):
        print(f"\n>>> Generating PORTRAIT for {name} (seed={seed})...")
        output_path = os.path.join(review_dir, f"{slug}_portrait_{timestamp}.png")
        # Use 1024x1024 for portrait
        result = await generate_image(
            prompt=prompts["portrait"],
            negative_prompt=prompts.get("negative", ENFORCED_NEGATIVE_PROMPT),
            size="1024*1024",
            seed=seed,
            n=1,
        )
        if result:
            # result is a list of URLs
            url = result[0]
            if url.startswith("http"):
                # Download URL
                import httpx
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        with open(output_path, 'wb') as f:
                            f.write(resp.content)
                        print(f"    ✓ Portrait saved: {output_path}")
                        results.append(output_path)
                    else:
                        print(f"    ✗ Failed to download: {resp.status_code}")
            else:
                # Local path
                print(f"    ✓ Result: {url}")
                results.append(url)
        else:
            print(f"    ✗ Portrait generation failed")

    if gen_type in ("three_view", "all"):
        print(f"\n>>> Generating THREE-VIEW for {name} (seed={seed})...")
        output_path = os.path.join(review_dir, f"{slug}_threeview_{timestamp}.png")
        # Use wider format for three-view: 1280x720
        result = await generate_image(
            prompt=prompts["three_view"],
            negative_prompt=prompts.get("negative", ENFORCED_NEGATIVE_PROMPT),
            size="1280*720",
            seed=seed,
            n=1,
        )
        if result:
            url = result[0]
            if url.startswith("http"):
                import httpx
                async with httpx.AsyncClient(timeout=60) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        with open(output_path, 'wb') as f:
                            f.write(resp.content)
                        print(f"    ✓ Three-view saved: {output_path}")
                        results.append(output_path)
                    else:
                        print(f"    ✗ Failed to download: {resp.status_code}")
            else:
                print(f"    ✓ Result: {url}")
                results.append(url)
        else:
            print(f"    ✗ Three-view generation failed")

    if results:
        print(f"\n=== Generation complete for {name} ===")
        print(f"Files saved in: {review_dir}")
        for r in results:
            print(f"  - {r}")
    else:
        print(f"\n=== No images generated for {name} ===")
        print("Check that DASHSCOPE_API_KEY is set in .env")

    return results


def main():
    parser = argparse.ArgumentParser(description="Generate single character for review")
    parser.add_argument("--character", "-c", required=True, help="Character name (Chinese)")
    parser.add_argument("--type", "-t", default="all", choices=["portrait", "three_view", "all"],
                       help="Type of generation")
    args = parser.parse_args()

    asyncio.run(generate_character(args.character, args.type))


if __name__ == "__main__":
    main()
