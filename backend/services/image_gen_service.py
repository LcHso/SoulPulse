"""DashScope AI image generation service (Wanx model).

Generates Instagram-style lifestyle photos for AI persona posts.
Uses the DashScope HTTP API for async image synthesis tasks.
"""

import asyncio
import uuid
from pathlib import Path

import httpx

from core.config import settings

_DASHSCOPE_IMAGE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
_DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

_STATIC_DIR = Path(__file__).parent.parent / "static" / "posts"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }


async def generate_image(prompt: str, size: str = "1024*1024", n: int = 1) -> list[str]:
    """Generate image(s) from a text prompt using DashScope Wanx model.

    Args:
        prompt: Detailed text description of the image to generate.
        size: Image dimensions, e.g. "1024*1024", "720*1280" (4:5 portrait).
        n: Number of images to generate (1-4).

    Returns:
        List of image URLs.
    """
    payload = {
        "model": settings.DASHSCOPE_IMAGE_MODEL,
        "input": {"prompt": prompt},
        "parameters": {"size": size, "n": n},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        # Submit async task
        resp = await client.post(_DASHSCOPE_IMAGE_URL, json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {data}")

        # Poll for result
        poll_url = _DASHSCOPE_TASK_URL.format(task_id=task_id)
        poll_headers = {"Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}"}

        for _ in range(60):  # max ~5 minutes
            await asyncio.sleep(5)
            poll_resp = await client.get(poll_url, headers=poll_headers)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            status = poll_data.get("output", {}).get("task_status")
            if status == "SUCCEEDED":
                results = poll_data["output"].get("results", [])
                return [r["url"] for r in results if r.get("url")]
            elif status in ("FAILED", "UNKNOWN"):
                msg = poll_data.get("output", {}).get("message", "Unknown error")
                raise RuntimeError(f"Image generation failed: {msg}")
            # else PENDING / RUNNING, keep polling

        raise TimeoutError("Image generation timed out after 5 minutes")


async def download_to_static(url: str, prefix: str = "post") -> str:
    """Download a remote image to local /static/posts/ and return the relative path.

    Args:
        url: Remote image URL (e.g. Aliyun OSS temporary link).
        prefix: Filename prefix for the saved file.

    Returns:
        Relative URL like '/static/posts/post_abc123.png'.
    """
    if not url:
        return ""
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:12]}.png"
    filepath = _STATIC_DIR / filename
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
        return f"/static/posts/{filename}"
    except Exception as e:
        print(f"[image_gen] Failed to download image: {e}")
        return url  # fallback to original URL
