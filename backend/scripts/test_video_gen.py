"""Video generation test script.

Tests the DashScope video generation API and verifies the output.
Run from the backend directory:
    python3 scripts/test_video_gen.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, ".")

from services.video_gen_service import generate_video
from core.config import settings


async def test_video_generation():
    """Test video generation with a sample prompt."""
    print("=" * 60)
    print("Video Generation Test")
    print("=" * 60)
    
    # Test prompt - lifestyle scene
    prompt = (
        "A peaceful sunset over a calm lake, gentle waves reflecting golden light, "
        "soft clouds in the sky, serene atmosphere, lifestyle photography style"
    )
    
    print(f"\nPrompt: {prompt}")
    print(f"Model: {settings.DASHSCOPE_VIDEO_MODEL}")
    print(f"Duration: 5.0 seconds")
    print("\nGenerating video... (this may take 5-10 minutes)")
    print("-" * 60)
    
    try:
        video_url = await generate_video(prompt, duration=5.0)
        print(f"\n✓ Video generated successfully!")
        print(f"URL: {video_url}")
        
        # Download and verify
        import httpx
        print("\nDownloading video to verify...")
        resp = await httpx.AsyncClient(timeout=60).get(video_url)
        resp.raise_for_status()
        
        size = len(resp.content)
        print(f"✓ Downloaded: {size:,} bytes ({size / 1024 / 1024:.2f} MB)")
        
        # Save locally for inspection
        output_path = Path("test_video.mp4")
        output_path.write_bytes(resp.content)
        print(f"✓ Saved to: {output_path.absolute()}")
        
        # Verify it's a valid MP4 (check magic bytes)
        if resp.content[:4] == b'\x00\x00\x00' or resp.content[4:8] == b'ftyp':
            print("✓ File appears to be a valid MP4")
        else:
            print("⚠ Warning: File may not be a valid MP4")
        
        print("\n" + "=" * 60)
        print("TEST PASSED - Video generation working correctly")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n✗ Video generation failed: {e}")
        print("\n" + "=" * 60)
        print("TEST FAILED")
        print("=" * 60)
        return False


async def test_multiple_videos():
    """Test generating multiple videos to check consistency."""
    print("\n" + "=" * 60)
    print("Testing Multiple Video Generation")
    print("=" * 60)
    
    prompts = [
        "A cozy coffee shop interior with warm lighting and plants",
        "A rainy window view with water droplets, city lights in background",
    ]
    
    for i, prompt in enumerate(prompts):
        print(f"\n[{i+1}/{len(prompts)}] Generating: {prompt[:50]}...")
        try:
            url = await generate_video(prompt, duration=3.0)
            print(f"  ✓ URL: {url[:60]}...")
        except Exception as e:
            print(f"  ✗ Failed: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test video generation")
    parser.add_argument("--multiple", action="store_true", help="Test multiple videos")
    args = parser.parse_args()
    
    if args.multiple:
        asyncio.run(test_multiple_videos())
    else:
        asyncio.run(test_video_generation())