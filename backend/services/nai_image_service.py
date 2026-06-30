"""
NovelAI Image Generation Service

Uses NovelAI's API for high-quality anime art generation.
API: https://image.novelai.net/ai/generate-image
Auth: Bearer token
Model: nai-diffusion-3 (NAI Diffusion Anime V3)
"""

import httpx
import io
import zipfile
import os
import time
from typing import Optional

from core.config import settings


class NAIImageService:
    """Service for generating images via NovelAI API."""

    BASE_URL = "https://image.novelai.net"
    GENERATE_ENDPOINT = "/ai/generate-image"

    # Default quality parameters
    DEFAULT_PARAMS = {
        "width": 1024,
        "height": 1024,
        "scale": 5.0,           # CFG scale (5-7 recommended for NAI)
        "sampler": "k_euler_ancestral",
        "steps": 28,
        "n_samples": 1,
        "ucPreset": 0,          # Heavy negative preset
        "qualityToggle": True,  # Auto-add quality tags
        "sm": True,             # SMEA sampling
        "sm_dyn": True,         # Dynamic SMEA
        "noise_schedule": "karras",
    }

    # Standard negative prompt for anime quality
    NEGATIVE_PROMPT = (
        "nsfw, lowres, {bad}, error, fewer, extra, missing, worst quality, "
        "jpeg artifacts, bad quality, watermark, unfinished, displeasing, "
        "chromatic aberration, signature, extra digits, artistic error, "
        "username, scan, [abstract], bad anatomy, bad hands, "
        "@_@, mismatched pupils, heart-shaped pupils, glowing eyes, "
        "extra fingers, fewer fingers, mutated hands, poorly drawn hands, "
        "malformed limbs, extra limbs, fused fingers, too many fingers, "
        "long neck, deformed, ugly, bad proportions, gross proportions, "
        "blurry, text, error, missing fingers"
    )

    # Quality boost positive prefix
    QUALITY_PREFIX = "masterpiece, best quality, very aesthetic, absurdres"

    def __init__(self):
        self.api_key = settings.NAI_API_KEY
        self.model = settings.NAI_MODEL

    async def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 1024,
        height: int = 1024,
        steps: int = 28,
        scale: float = 5.0,
        seed: Optional[int] = None,
        sampler: str = "k_euler_ancestral",
        n_samples: int = 1,
    ) -> Optional[bytes]:
        """
        Generate an image using NovelAI API.

        Args:
            prompt: Danbooru-style tags for generation
            negative_prompt: Tags to avoid (uses default if None)
            width: Image width (must be multiple of 64)
            height: Image height (must be multiple of 64)
            steps: Number of sampling steps (28 recommended)
            scale: CFG scale (5.0-7.0 for anime)
            seed: Random seed for reproducibility
            sampler: Sampling method
            n_samples: Number of images to generate

        Returns:
            Image bytes (PNG) or None if failed
        """
        if not self.api_key:
            print("[NAI] Error: NAI_API_KEY not configured")
            return None

        # Build full prompt with quality prefix
        full_prompt = f"{self.QUALITY_PREFIX}, {prompt}"
        full_negative = negative_prompt or self.NEGATIVE_PROMPT

        # Build request payload
        payload = {
            "input": full_prompt,
            "model": self.model,
            "action": "generate",
            "parameters": {
                "width": width,
                "height": height,
                "scale": scale,
                "sampler": sampler,
                "steps": steps,
                "n_samples": n_samples,
                "ucPreset": 0,
                "qualityToggle": True,
                "sm": True,
                "sm_dyn": True,
                "noise_schedule": "karras",
                "negative_prompt": full_negative,
                "seed": seed if seed is not None else int(time.time()) % 2**32,
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/zip",  # NAI returns zip containing the image
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}{self.GENERATE_ENDPOINT}",
                    json=payload,
                    headers=headers,
                )

                if response.status_code == 200:
                    # NAI returns a zip file containing the PNG
                    zip_data = io.BytesIO(response.content)
                    with zipfile.ZipFile(zip_data, "r") as zf:
                        # Get the first (usually only) image file
                        image_names = [n for n in zf.namelist() if n.endswith(".png")]
                        if image_names:
                            return zf.read(image_names[0])
                    print("[NAI] Error: No PNG found in response zip")
                    return None
                elif response.status_code == 429:
                    print("[NAI] Rate limited. Waiting before retry...")
                    return None
                else:
                    print(f"[NAI] Error {response.status_code}: {response.text[:200]}")
                    return None

        except Exception as e:
            print(f"[NAI] Request failed: {e}")
            return None

    async def generate_portrait(
        self,
        character_tags: str,
        seed: Optional[int] = None,
        size: int = 1024,
    ) -> Optional[bytes]:
        """Generate a character portrait (bust/face focus)."""
        portrait_prompt = (
            f"1person, portrait, upper body, looking at viewer, "
            f"simple background, {character_tags}"
        )
        return await self.generate_image(
            prompt=portrait_prompt,
            width=size,
            height=size,
            seed=seed,
            scale=5.5,
        )

    async def generate_avatar(
        self,
        character_tags: str,
        seed: Optional[int] = None,
    ) -> Optional[bytes]:
        """Generate a character avatar (close-up face)."""
        avatar_prompt = (
            f"1person, face focus, close-up, looking at viewer, "
            f"simple background, {character_tags}"
        )
        return await self.generate_image(
            prompt=avatar_prompt,
            width=512,
            height=512,
            seed=seed,
            scale=6.0,
        )

    async def generate_scene(
        self,
        character_tags: str,
        scene_tags: str,
        orientation: str = "landscape",
        seed: Optional[int] = None,
    ) -> Optional[bytes]:
        """
        Generate a scene illustration with character.

        Args:
            character_tags: Character appearance tags
            scene_tags: Scene/environment tags
            orientation: "landscape" (1216x832), "portrait" (832x1216), "square" (1024x1024)
        """
        sizes = {
            "landscape": (1216, 832),
            "portrait": (832, 1216),
            "square": (1024, 1024),
        }
        w, h = sizes.get(orientation, (1216, 832))

        scene_prompt = f"1person, {character_tags}, {scene_tags}"
        return await self.generate_image(
            prompt=scene_prompt,
            width=w,
            height=h,
            seed=seed,
            scale=5.0,
        )

    async def generate_post_image(
        self,
        character_tags: str,
        scenario_tags: str,
        orientation: str = "portrait",
        seed: Optional[int] = None,
    ) -> Optional[bytes]:
        """Generate an image for a social media post."""
        sizes = {
            "landscape": (1216, 832),
            "portrait": (832, 1216),
            "square": (1024, 1024),
        }
        w, h = sizes.get(orientation, (832, 1216))

        post_prompt = f"1person, {character_tags}, {scenario_tags}, detailed background"
        return await self.generate_image(
            prompt=post_prompt,
            width=w,
            height=h,
            seed=seed,
        )

    async def save_image(self, image_bytes: bytes, filepath: str) -> str:
        """Save image bytes to a file path. Returns the relative URL path."""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        # Return relative path from static dir for URL serving
        if "/static/" in filepath:
            return "/static/" + filepath.split("/static/")[-1]
        return filepath


# Singleton instance
nai_service = NAIImageService()
