"""M2: AIGC Aesthetic Control endpoints (post review, visual DNA, story assets)"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user, audit_log, _to_utc_iso

router = APIRouter(tags=["admin-aigc"])


# ── Pydantic Models ──

class PostOut(BaseModel):
    id: int
    ai_id: int
    ai_name: str
    ai_avatar: str
    media_url: str
    caption: str
    status: int
    created_at: str

class PendingPostsResponse(BaseModel):
    posts: list[PostOut]
    total: int
    has_more: bool

class RegenerateRequest(BaseModel):
    new_caption: str | None = None

class VisualDnaCreate(BaseModel):
    persona_id: int
    face_url: str = ""
    style_preset_json: str = "{}"
    version_note: str = ""

class VisualDnaOut(BaseModel):
    id: int
    persona_id: int
    face_url: str
    style_preset_json: str
    version_note: str
    created_by: int
    created_at: str


# ── Post Review (migrated from old admin.py) ──

@router.get("/posts/pending", response_model=PendingPostsResponse)
async def list_pending_posts(
    limit: int = 20,
    offset: int = 0,
    ai_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.post import Post
    from models.ai_persona import AIPersona

    query = (
        select(Post, AIPersona)
        .join(AIPersona, Post.ai_id == AIPersona.id)
        .where(Post.status == 0)
        .order_by(Post.created_at.desc())
    )
    if ai_id:
        query = query.where(Post.ai_id == ai_id)

    count_query = select(func.count()).select_from(Post).where(Post.status == 0)
    if ai_id:
        count_query = count_query.where(Post.ai_id == ai_id)
    total = (await db.execute(count_query)).scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    rows = result.all()

    posts = [
        PostOut(
            id=post.id, ai_id=post.ai_id, ai_name=persona.name,
            ai_avatar=persona.avatar_url, media_url=post.media_url,
            caption=post.caption, status=post.status,
            created_at=_to_utc_iso(post.created_at),
        )
        for post, persona in rows
    ]

    return PendingPostsResponse(posts=posts, total=total, has_more=offset + limit < total)


@router.post("/posts/{post_id}/approve")
async def approve_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.post import Post
    from models.ai_persona import AIPersona
    from models.follow import Follow
    from models.notification import Notification

    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status != 0:
        raise HTTPException(status_code=400, detail="Post is not pending")

    post.status = 1
    await db.flush()

    persona_r = await db.execute(select(AIPersona).where(AIPersona.id == post.ai_id))
    persona = persona_r.scalar_one_or_none()
    if persona:
        follower_r = await db.execute(select(Follow.user_id).where(Follow.ai_id == persona.id))
        for (uid,) in follower_r.all():
            db.add(Notification(
                user_id=uid, type="new_post",
                title=f"{persona.name} shared a new post",
                body=post.caption[:200],
                data_json=f'{{"post_id": {post.id}, "ai_id": {persona.id}, "ai_name": "{persona.name}"}}',
            ))

    await db.commit()
    return {"message": "Post approved", "post_id": post_id, "status": 1}


@router.post("/posts/{post_id}/reject")
async def reject_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.post import Post

    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.status != 0:
        raise HTTPException(status_code=400, detail="Post is not pending")

    post.status = 2
    await db.commit()
    return {"message": "Post rejected", "post_id": post_id, "status": 2}


@router.post("/posts/{post_id}/regenerate")
async def regenerate_post_image(
    post_id: int,
    request: RegenerateRequest | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.post import Post
    from models.ai_persona import AIPersona

    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    persona_r = await db.execute(select(AIPersona).where(AIPersona.id == post.ai_id))
    persona = persona_r.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    if not persona.base_face_url:
        raise HTTPException(status_code=400, detail="Persona has no base_face_url")

    new_caption = (request.new_caption if request else None) or post.caption

    from services.image_gen_service import (
        generate_image_with_face_ref, download_to_static,
        ENFORCED_NEGATIVE_PROMPT,
    )
    from services.aliyun_ai_service import generate_image_prompt

    try:
        img_prompt = await generate_image_prompt(
            persona_prompt=persona.personality_prompt,
            style_tags=persona.ins_style_tags,
            caption=new_caption,
            visual_description=persona.visual_prompt_tags,
        )
        urls = await generate_image_with_face_ref(
            prompt=img_prompt, face_ref_url=persona.base_face_url,
            size="720*1280", n=1, persona_id=persona.id,
            negative_prompt=ENFORCED_NEGATIVE_PROMPT,
        )
        if urls:
            new_url = await download_to_static(urls[0], prefix=f"regen_{post.id}")
            post.media_url = new_url
            post.caption = new_caption
            await db.commit()
            return {"message": "Image regenerated", "post_id": post_id, "media_url": new_url, "status": 0}
        raise HTTPException(status_code=500, detail="Image generation failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {str(e)}")


# ── Post listing (all statuses) ──

@router.get("/posts/all")
async def list_all_posts(
    limit: int = 20,
    offset: int = 0,
    status: int | None = None,
    ai_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.post import Post
    from models.ai_persona import AIPersona

    query = (
        select(Post, AIPersona)
        .join(AIPersona, Post.ai_id == AIPersona.id)
        .order_by(Post.created_at.desc())
    )
    count_q = select(func.count()).select_from(Post)
    if status is not None:
        query = query.where(Post.status == status)
        count_q = count_q.where(Post.status == status)
    if ai_id:
        query = query.where(Post.ai_id == ai_id)
        count_q = count_q.where(Post.ai_id == ai_id)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    rows = result.all()

    posts = [
        PostOut(
            id=post.id, ai_id=post.ai_id, ai_name=persona.name,
            ai_avatar=persona.avatar_url, media_url=post.media_url,
            caption=post.caption, status=post.status,
            created_at=_to_utc_iso(post.created_at),
        )
        for post, persona in rows
    ]
    return {"posts": posts, "total": total, "has_more": offset + limit < total}


# ── Delete post ──

@router.delete("/posts/{post_id}")
async def delete_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """删除帖子及其关联的评论、点赞、收藏记录。"""
    from models.post import Post
    from sqlalchemy import text

    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Cascade cleanup
    await db.execute(text("DELETE FROM comments WHERE post_id = :pid"), {"pid": post_id})
    await db.execute(text("DELETE FROM user_likes WHERE post_id = :pid"), {"pid": post_id})
    await db.execute(text("DELETE FROM saved_posts WHERE post_id = :pid"), {"pid": post_id})

    await db.delete(post)
    await db.commit()
    return {"message": "Post deleted", "post_id": post_id}


# ── Visual DNA ──

@router.get("/visual-dna/{persona_id}")
async def list_visual_dna(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.visual_dna_version import VisualDnaVersion
    result = await db.execute(
        select(VisualDnaVersion)
        .where(VisualDnaVersion.persona_id == persona_id)
        .order_by(VisualDnaVersion.created_at.desc())
    )
    versions = result.scalars().all()
    return [
        VisualDnaOut(
            id=v.id, persona_id=v.persona_id, face_url=v.face_url,
            style_preset_json=v.style_preset_json, version_note=v.version_note,
            created_by=v.created_by, created_at=_to_utc_iso(v.created_at),
        )
        for v in versions
    ]


@router.post("/visual-dna")
async def create_visual_dna(
    req: VisualDnaCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.visual_dna_version import VisualDnaVersion
    from models.ai_persona import AIPersona

    # Verify persona exists
    p_r = await db.execute(select(AIPersona).where(AIPersona.id == req.persona_id))
    if not p_r.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Persona not found")

    entry = VisualDnaVersion(
        persona_id=req.persona_id,
        face_url=req.face_url,
        style_preset_json=req.style_preset_json,
        version_note=req.version_note,
        created_by=admin.id,
    )
    db.add(entry)

    # Also update the persona's base_face_url if face_url provided
    if req.face_url:
        persona = (await db.execute(select(AIPersona).where(AIPersona.id == req.persona_id))).scalar_one()
        persona.base_face_url = req.face_url

    await db.commit()
    await db.refresh(entry)
    return VisualDnaOut(
        id=entry.id, persona_id=entry.persona_id, face_url=entry.face_url,
        style_preset_json=entry.style_preset_json, version_note=entry.version_note,
        created_by=entry.created_by, created_at=_to_utc_iso(entry.created_at),
    )


@router.delete("/visual-dna/{version_id}")
async def delete_visual_dna(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.visual_dna_version import VisualDnaVersion
    result = await db.execute(select(VisualDnaVersion).where(VisualDnaVersion.id == version_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Visual DNA version not found")
    await db.delete(entry)
    await db.commit()
    return {"message": "Deleted", "id": version_id}


# ── Story assets ──

@router.get("/stories")
async def list_stories(
    limit: int = 20,
    offset: int = 0,
    ai_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.story import Story
    from models.ai_persona import AIPersona

    query = (
        select(Story, AIPersona)
        .join(AIPersona, Story.ai_id == AIPersona.id)
        .order_by(Story.created_at.desc())
    )
    if ai_id:
        query = query.where(Story.ai_id == ai_id)

    count_q = select(func.count()).select_from(Story)
    if ai_id:
        count_q = count_q.where(Story.ai_id == ai_id)
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    rows = result.all()

    stories = []
    for story, persona in rows:
        stories.append({
            "id": story.id,
            "ai_id": story.ai_id,
            "ai_name": persona.name,
            "media_url": story.media_url,
            "media_type": story.media_type,
            "caption": story.caption,
            "created_at": _to_utc_iso(story.created_at),
        })

    return {"stories": stories, "total": total, "has_more": offset + limit < total}


@router.delete("/stories/{story_id}")
async def delete_story(
    story_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.story import Story
    result = await db.execute(select(Story).where(Story.id == story_id))
    story = result.scalar_one_or_none()
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    await db.delete(story)
    await db.commit()
    return {"message": "Story deleted", "id": story_id}
