"""DashScope AI image generation service (Wanx model).

Generates Instagram-style lifestyle photos for AI persona posts.
Uses the DashScope HTTP API for async image synthesis tasks.

Features:
- Standard text-to-image generation
- Face reference for consistent character appearance
- Deterministic seed per persona for style consistency
"""

import asyncio
import hashlib
import uuid
from pathlib import Path

import httpx

from core.config import settings

_DASHSCOPE_IMAGE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"
_DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

_STATIC_DIR = Path(__file__).parent.parent / "static" / "posts"

# Default negative prompt for quality protection
DEFAULT_NEGATIVE_PROMPT = (
    "worst quality, low quality, deformed face, bad anatomy, "
    "blurry, out of focus, ugly, duplicate, morbid, mutilated, "
    "extra fingers, poorly drawn hands, poorly drawn face, mutation"
)


def _get_persona_seed(persona_id: int) -> int:
    """Generate deterministic seed from persona ID for consistent image style.

    Same persona_id always produces the same seed, ensuring visual consistency
    across different generated images for the same character.

    Args:
        persona_id: The AI persona's unique identifier.

    Returns:
        Integer seed for image generation API.
    """
    # Use MD5 hash of persona_id to create a stable, unique seed
    hex_hash = hashlib.md5(f"persona_{persona_id}".encode()).hexdigest()[:8]
    return int(hex_hash, 16)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }


async def generate_image(
    prompt: str,
    size: str = "1024*1024",
    n: int = 1,
    persona_id: int | None = None,
    negative_prompt: str | None = None,
) -> list[str]:
    """Generate image(s) from a text prompt using DashScope Wanx model.

    Args:
        prompt: Detailed text description of the image to generate.
        size: Image dimensions, e.g. "1024*1024", "720*1280" (4:5 portrait).
        n: Number of images to generate (1-4).
        persona_id: AI persona ID for consistent image style (deterministic seed).
        negative_prompt: Quality protection prompts. Optional.

    Returns:
        List of image URLs.
    """
    parameters = {"size": size, "n": n}

    # Add negative prompt for quality protection
    if negative_prompt:
        parameters["negative_prompt"] = negative_prompt

    # Add deterministic seed for persona consistency
    if persona_id is not None:
        parameters["seed"] = _get_persona_seed(persona_id)

    payload = {
        "model": settings.DASHSCOPE_IMAGE_MODEL,
        "input": {"prompt": prompt},
        "parameters": parameters,
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


async def generate_image_with_face_ref(
    prompt: str,
    face_ref_url: str,
    size: str = "720*1280",
    n: int = 1,
    persona_id: int | None = None,
    negative_prompt: str | None = None,
) -> list[str]:
    """Generate image with face reference for consistent character appearance.

    This is the core of the Visual Identity (VI) system. It uses a base portrait
    as a face reference to ensure all generated images have the same character face.

    Args:
        prompt: Scene/action description WITHOUT face details.
                Example: "1boy, working out at gym, lifting weights, cinematic lighting"
        face_ref_url: URL of the base portrait image (the "ID photo").
        size: Image dimensions, default "720*1280" (4:5 portrait for Instagram).
        n: Number of images to generate (1-4).
        persona_id: AI persona ID for deterministic seed.
        negative_prompt: Quality protection prompts. Uses DEFAULT_NEGATIVE_PROMPT if None.

    Returns:
        List of generated image URLs.

    Example usage:
        # Step 1: Character has a base_face_url stored in database
        # Step 2: When generating post, only describe scene:
        prompt = "1boy, sitting in a cozy cafe, reading a book, soft window light"
        # Step 3: The face will match the base_face_url
    """
    parameters = {
        "size": size,
        "n": n,
        "negative_prompt": negative_prompt or DEFAULT_NEGATIVE_PROMPT,
    }

    # Add deterministic seed for persona style consistency
    if persona_id is not None:
        parameters["seed"] = _get_persona_seed(persona_id)

    # Build input with face reference
    input_data = {
        "prompt": prompt,
        "ref_image": face_ref_url,
        "ref_mode": "face_ref",  # Face reference mode
        "ref_strength": 0.8,  # Weight for face similarity (0-1)
    }

    payload = {
        "model": settings.DASHSCOPE_IMAGE_MODEL,
        "input": input_data,
        "parameters": parameters,
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

        raise TimeoutError("Image generation timed out after 5 minutes")


async def generate_base_portrait(
    visual_prompt_tags: str,
    gender: str = "male",
    style: str = "photorealistic",
) -> str:
    """Generate a high-quality base portrait for a character.

    This creates the "ID photo" that will be used for all subsequent
    image generations to maintain face consistency.

    Args:
        visual_prompt_tags: Fixed visual traits.
            Example: "silver hair, sharp jawline, deep blue eyes"
        gender: Character gender ("male" or "female").
        style: Visual style ("photorealistic", "anime", etc.)

    Returns:
        URL of the generated base portrait.
    """
    gender_tag = "1boy" if gender == "male" else "1girl"

    # Build high-quality portrait prompt
    prompt = (
        f"Masterpiece, best quality, 8k, {style}, {gender_tag}, "
        f"{visual_prompt_tags}, "
        f"high-end fashion photography, professional portrait, "
        f"soft studio lighting, clean background, looking at camera, "
        f"neutral expression, upper body shot"
    )

    negative = (
        "worst quality, low quality, deformed face, bad anatomy, "
        "blurry, out of focus, ugly, profile, side view, "
        "multiple people, crowd, busy background, harsh lighting"
    )

    urls = await generate_image(
        prompt=prompt,
        size="1024*1024",  # Square for portrait
        n=1,
        negative_prompt=negative,
    )

    return urls[0] if urls else ""
