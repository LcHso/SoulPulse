"""DashScope AI video generation service.

Generates short lifestyle video clips for AI persona Stories / posts.
Uses the DashScope HTTP API for async video synthesis tasks.
"""

import asyncio
import httpx

from core.config import settings

_DASHSCOPE_VIDEO_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2video/video-synthesis"
_DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }


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
        "parameters": {"duration": duration},
    }

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(_DASHSCOPE_VIDEO_URL, json=payload, headers=_headers())
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in response: {data}")

        # Poll — video generation is slower, allow up to 10 minutes
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
