"""Generate initial posts for StarLin (林星野, ID=5).

Creates 3 AI-generated posts with images using the same pipeline as the scheduler.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from core.database import async_session, init_db
from models.ai_persona import AIPersona
from models.post import Post
from services.aliyun_ai_service import generate_post_caption, generate_image_prompt
from services.image_gen_service import generate_image_with_face_ref


CAPTIONS = [
    "练舞到凌晨两点，终于把新舞台的动作磨完了！虽然累但超有成就感～ 明天演出等我呀✨",
    "今天偷偷溜去便利店买了草莓牛奶，被经纪人抓到了哈哈...减肥计划又泡汤了(◍•ᴗ•◍)",
    "写了一首新歌，关于星星和月亮的...录音棚的灯光好温柔，希望你们会喜欢🌙",
]


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

        print(f"[gen] Generating 3 posts for {persona.name} (ID={persona.id})")
        print(f"[gen] base_face_url: {persona.base_face_url}")

        for i, caption in enumerate(CAPTIONS):
            print(f"\n[gen] Post {i+1}/3: {caption[:50]}...")

            # Generate image prompt from caption
            try:
                img_prompt = await generate_image_prompt(
                    persona_prompt=persona.personality_prompt,
                    style_tags=persona.ins_style_tags,
                    caption=caption,
                    visual_description=persona.visual_prompt_tags,
                )
                print(f"  Image prompt: {img_prompt[:80]}...")
            except Exception as e:
                print(f"  Image prompt error: {e}")
                continue

            # Generate image with face ref
            media_url = ""
            try:
                urls = await generate_image_with_face_ref(
                    prompt=img_prompt,
                    face_ref_url=persona.base_face_url,
                    size="720*1280",
                    n=1,
                    persona_id=persona.id,
                )
                media_url = urls[0] if urls else ""
                print(f"  Image: {media_url[:80]}...")
            except Exception as e:
                print(f"  Image gen error: {e}")

            # Create post
            post = Post(
                ai_id=persona.id,
                media_url=media_url,
                caption=caption,
            )
            db.add(post)
            await db.commit()
            print(f"  Saved post (id will be assigned)")

        print("\n[gen] Done! 3 posts created for StarLin.")


if __name__ == "__main__":
    asyncio.run(main())
