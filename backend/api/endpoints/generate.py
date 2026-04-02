from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from core.security import get_current_user
from models.user import User
from models.post import Post
from models.ai_persona import AIPersona
from services.aliyun_ai_service import generate_post_caption, generate_image_prompt
from services.image_gen_service import generate_image, generate_image_with_face_ref
from services.video_gen_service import generate_video, generate_video_with_image_ref

router = APIRouter(prefix="/api/generate", tags=["generate"])


class GeneratePostRequest(BaseModel):
    ai_id: int
    media_type: str = "image"  # "image" or "video"


class GeneratePostResponse(BaseModel):
    post_id: int
    caption: str
    media_url: str
    media_type: str


@router.post("/post", response_model=GeneratePostResponse)
async def generate_post(
    body: GeneratePostRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a new AI post with AI-created caption + image/video."""
    persona_result = await db.execute(select(AIPersona).where(AIPersona.id == body.ai_id))
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="AI persona not found")

    # Step 1: Generate caption
    caption = await generate_post_caption(
        persona_prompt=persona.personality_prompt,
        style_tags=persona.ins_style_tags,
    )

    # Step 2: Generate image prompt from caption (with visual tags for consistency)
    img_prompt = await generate_image_prompt(
        persona_prompt=persona.personality_prompt,
        style_tags=persona.ins_style_tags,
        caption=caption,
        visual_description=persona.visual_prompt_tags,
    )

    base_face_url = getattr(persona, 'base_face_url', None)

    # Step 3: Generate media
    media_url = ""
    if body.media_type == "video":
        try:
            if base_face_url:
                media_url = await generate_video_with_image_ref(
                    prompt=img_prompt, image_ref_url=base_face_url, duration=5.0,
                )
            else:
                media_url = await generate_video(prompt=img_prompt, duration=5.0)
        except Exception as e:
            # Fallback to image if video fails
            print(f"[generate] Video gen failed, falling back to image: {e}")
            body.media_type = "image"

    if body.media_type == "image" or not media_url:
        try:
            if base_face_url:
                urls = await generate_image_with_face_ref(
                    prompt=img_prompt, face_ref_url=base_face_url,
                    size="720*1280", n=1, persona_id=persona.id,
                )
            else:
                urls = await generate_image(prompt=img_prompt, size="720*1280", n=1)
            media_url = urls[0] if urls else ""
        except Exception as e:
            print(f"[generate] Image gen failed: {e}")
            media_url = ""

    # Step 4: Save post
    post = Post(
        ai_id=persona.id,
        media_url=media_url,
        caption=caption,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    return GeneratePostResponse(
        post_id=post.id,
        caption=caption,
        media_url=media_url,
        media_type=body.media_type,
    )
