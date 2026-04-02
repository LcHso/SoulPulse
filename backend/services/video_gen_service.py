"""DashScope AI video generation service.

Generates short lifestyle video clips for AI persona Stories / posts.
Uses the DashScope HTTP API for async video synthesis tasks.

Features:
- Image-to-video generation (wan2.6-i2v-flash)
- Text-to-video fallback
- Image reference for consistent character appearance in videos
"""

import asyncio
import httpx

from core.config import settings


def _resolve_public_url(path: str) -> str:
    """Convert a local path like /static/posts/xxx.png to a full public URL."""
    if path.startswith(("http://", "https://")):
        return path
    return f"{settings.PUBLIC_URL.rstrip('/')}{path}"


_DASHSCOPE_VIDEO_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
_DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }


async def _poll_task(client: httpx.AsyncClient, task_id: str) -> str:
    """Poll a DashScope async task until completion. Returns the video URL."""
    poll_url = _DASHSCOPE_TASK_URL.format(task_id=task_id)
    poll_headers = {"Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}"}

    for _ in range(120):
        await asyncio.sleep(5)
        poll_resp = await client.get(poll_url, headers=poll_headers)
        poll_resp.raise_for_status()
        poll_data = poll_resp.json()

        status = poll_data.get("output", {}).get("task_status")
        if status == "SUCCEEDED":
            video_url = poll_data["output"].get("video_url", "")
            if not video_url:
                results = poll_data["output"].get("results", [])
                if results:
                    video_url = results[0].get("url", "")
            return video_url
        elif status in ("FAILED", "UNKNOWN"):
            msg = poll_data.get("output", {}).get("message", "Unknown error")
            raise RuntimeError(f"Video generation failed: {msg}")

    raise TimeoutError("Video generation timed out after 10 minutes")


async def generate_video(prompt: str, duration: float = 5.0) -> str:
    """Generate a short video from a text prompt using DashScope.

    Args:
        prompt: Detailed description of the video scene.
        duration: Target duration in seconds (typically 3-10s).

    Returns:
        URL of the generated video.
    """
    payload = {
        "model": settings.DASHSCOPE_VIDEO_MODEL,
        "input": {"prompt": prompt},
        "parameters": {"duration": int(duration)},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(_DASHSCOPE_VIDEO_URL, json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {data}")

        return await _poll_task(client, task_id)


async def generate_video_with_image_ref(
    prompt: str,
    image_ref_url: str,
    duration: float = 5.0,
) -> str:
    """Generate a video from an image reference (image-to-video).

    Uses the base portrait as the source image for video generation,
    ensuring the character in the video matches the one in posts.

    Args:
        prompt: Scene/action description for the video.
        image_ref_url: URL of the reference image (base portrait).
        duration: Target duration in seconds (typically 3-10s).

    Returns:
        URL of the generated video.
    """
    resolved_ref_url = _resolve_public_url(image_ref_url)
    payload = {
        "model": settings.DASHSCOPE_VIDEO_MODEL,
        "input": {
            "prompt": prompt,
            "img_url": resolved_ref_url,
        },
        "parameters": {
            "duration": int(duration),
            "resolution": "720P",
        },
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(_DASHSCOPE_VIDEO_URL, json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {data}")

        return await _poll_task(client, task_id)
