"""DashScope AI image generation service (Wanx model).

Generates Instagram-style lifestyle photos for AI persona posts.
Uses the DashScope HTTP API for async image synthesis tasks.
"""

import asyncio
import httpx

from core.config import settings

_DASHSCOPE_IMAGE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
_DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"


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
