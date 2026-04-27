"""Regenerate images for posts that have empty media_url.

Reads the post's caption to generate an image prompt, then generates an image
using the persona's base_face_url for consistency.
"""
import asyncio
import sys
import os

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from core.database import async_session
from models.post import Post
from models.ai_persona import AIPersona
from services.aliyun_ai_service import generate_image_prompt
from services.image_gen_service import generate_image, generate_image_with_face_ref


async def regenerate_missing_images():
    async with async_session() as db:
        # Find posts with empty media_url
        result = await db.execute(
            select(Post).where((Post.media_url == None) | (Post.media_url == "")).order_by(Post.id)
        )
        posts = result.scalars().all()

        if not posts:
            print("No posts with empty media_url found.")
            return

        # Load all personas
        persona_result = await db.execute(select(AIPersona))
        personas = {p.id: p for p in persona_result.scalars().all()}

        print(f"Found {len(posts)} posts with empty media_url")

        for post in posts:
            persona = personas.get(post.ai_id)
            if not persona:
                print(f"  Post {post.id}: no persona for ai_id={post.ai_id}, skipping")
                continue

            print(f"  Post {post.id} (ai_id={post.ai_id}, {persona.name}): regenerating image...")

            try:
                # Generate image prompt from the existing caption
                img_prompt = await generate_image_prompt(
                    persona_prompt=persona.personality_prompt,
                    style_tags=persona.ins_style_tags,
                    caption=post.caption,
                    visual_description=persona.visual_prompt_tags,
                )
                print(f"    Image prompt: {img_prompt[:80]}...")

                # Generate the image with face reference
                base_face_url = getattr(persona, "base_face_url", None)
                if base_face_url:
                    urls = await generate_image_with_face_ref(
                        prompt=img_prompt, face_ref_url=base_face_url,
                        size="720*1280", n=1, persona_id=persona.id,
                    )
                else:
                    urls = await generate_image(prompt=img_prompt, size="720*1280", n=1)

                if urls:
                    post.media_url = urls[0]
                    print(f"    Success: {urls[0]}")
                else:
                    print(f"    Warning: no URLs returned")
            except Exception as e:
                print(f"    Error: {e}")
                continue

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(regenerate_missing_images())
