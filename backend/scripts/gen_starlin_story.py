"""Generate a video story for StarLin using wan2.6-i2v-flash and publish it."""
import asyncio
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from core.database import async_session, init_db
from models.ai_persona import AIPersona
from models.story import Story
from services.video_gen_service import generate_video_with_image_ref


async def main():
    await init_db()
    async with async_session() as db:
        result = await db.execute(
            select(AIPersona).where(AIPersona.name == "林星野")
        )
        persona = result.scalar_one_or_none()
        if not persona:
            print("StarLin persona not found!")
            return

        print(f"[video] Generating story video for {persona.name} (ID={persona.id})")
        print(f"[video] base_face_url: {persona.base_face_url}")

        prompt = "A young Chinese male idol in a white hoodie with star print, practicing dance moves in a bright modern dance studio, soft warm lighting, smooth camera movement, cinematic"
        caption = "练舞结束！给你们看看练习室的日落～ 好美呀✨"

        print(f"[video] Prompt: {prompt}")
        print(f"[video] Generating video (this may take a few minutes)...")

        try:
            video_url = await generate_video_with_image_ref(
                prompt=prompt,
                image_ref_url=persona.base_face_url,
                duration=5.0,
            )
            print(f"[video] Video URL: {video_url}")
        except Exception as e:
            print(f"[video] ERROR: {e}")
            return

        if not video_url:
            print("[video] Empty video URL, aborting.")
            return

        # Create story record
        now = datetime.now(timezone.utc)
        story = Story(
            ai_id=persona.id,
            video_url=video_url,
            caption=caption,
            expires_at=now + timedelta(hours=24),
        )
        db.add(story)
        await db.commit()
        print(f"[video] Story published! Expires in 24h.")
        print(f"[video] Done!")


if __name__ == "__main__":
    asyncio.run(main())
