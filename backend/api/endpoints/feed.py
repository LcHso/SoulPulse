from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from typing import Optional
import asyncio
import random
import logging
import httpx

from core.database import get_db, async_session
from core.security import get_current_user
from models.user import User
from models.post import Post
from models.ai_persona import AIPersona
from models.interaction import Interaction
from models.story import Story
from models.comment import Comment
from services import memory_service
from services.aliyun_ai_service import generate_comment_reply

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feed", tags=["feed"])


class PostOut(BaseModel):
    id: int
    ai_id: int
    ai_name: str
    ai_avatar: str
    media_url: str
    caption: str
    like_count: int
    is_close_friend: bool
    created_at: str


@router.get("/posts", response_model=list[PostOut])
async def get_posts(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch the Ins-style feed of posts."""
    result = await db.execute(
        select(Post, AIPersona)
        .join(AIPersona, Post.ai_id == AIPersona.id)
        .order_by(Post.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    # Batch-load user's interactions for intimacy-based filtering
    ai_ids = list({post.ai_id for post, _ in rows})
    if ai_ids:
        interaction_result = await db.execute(
            select(Interaction).where(
                Interaction.user_id == current_user.id,
                Interaction.ai_id.in_(ai_ids),
            )
        )
        intimacy_map = {
            i.ai_id: i.intimacy_score
            for i in interaction_result.scalars().all()
        }
    else:
        intimacy_map = {}

    # Filter: exclude close-friend posts for users with intimacy < 6.0
    filtered = []
    for post, persona in rows:
        if post.is_close_friend:
            intimacy = intimacy_map.get(post.ai_id, 0.0)
            if intimacy < 6.0:
                continue
        filtered.append((post, persona))

    return [
        PostOut(
            id=post.id,
            ai_id=post.ai_id,
            ai_name=persona.name,
            ai_avatar=persona.avatar_url,
            media_url=post.media_url,
            caption=post.caption,
            like_count=post.like_count,
            is_close_friend=post.is_close_friend,
            created_at=post.created_at.isoformat(),
        )
        for post, persona in filtered
    ]


@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Like a post: increment like count and intimacy +1."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    post.like_count += 1

    # Update intimacy
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id == post.ai_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    if interaction:
        interaction.intimacy_score = min(interaction.intimacy_score + 1, 10.0)
    else:
        interaction = Interaction(
            user_id=current_user.id,
            ai_id=post.ai_id,
            intimacy_score=1.0,
        )
        db.add(interaction)

    await db.commit()
    return {"liked": True, "like_count": post.like_count}


@router.get("/image-proxy")
async def image_proxy(url: str = Query(...)):
    """Proxy external image to avoid CORS issues in Flutter web."""
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/png")
        return StreamingResponse(
            iter([resp.content]),
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )


class StoryOut(BaseModel):
    id: int
    ai_id: int
    ai_name: str
    ai_avatar: str
    video_url: str
    caption: str
    created_at: str
    expires_at: str


@router.get("/stories", response_model=list[StoryOut])
async def get_stories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch unexpired stories with AI persona info."""
    result = await db.execute(
        select(Story, AIPersona)
        .join(AIPersona, Story.ai_id == AIPersona.id)
        .order_by(Story.created_at.desc())
    )
    rows = result.all()

    # Filter expired stories in Python (SQLite datetime comparison is unreliable)
    now = datetime.now(timezone.utc)
    return [
        StoryOut(
            id=story.id,
            ai_id=story.ai_id,
            ai_name=persona.name,
            ai_avatar=persona.avatar_url,
            video_url=story.video_url,
            caption=story.caption,
            created_at=story.created_at.isoformat(),
            expires_at=story.expires_at.isoformat(),
        )
        for story, persona in rows
        if story.expires_at.astimezone(timezone.utc) > now
    ]


# ── Comment system with delayed AI reply ─────────────────────────────


class CommentIn(BaseModel):
    content: str


class CommentOut(BaseModel):
    id: int
    post_id: int
    user_id: Optional[int]
    ai_id: Optional[int]
    is_ai_reply: bool
    reply_to: Optional[int]
    content: str
    author_name: str
    author_avatar: str
    created_at: str


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
async def get_comments(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch all comments for a post, ordered by time."""
    result = await db.execute(
        select(Comment).where(Comment.post_id == post_id).order_by(Comment.created_at.asc())
    )
    comments = result.scalars().all()

    # Batch-load user and AI persona names
    user_ids = [c.user_id for c in comments if c.user_id]
    ai_ids = [c.ai_id for c in comments if c.ai_id]

    user_map = {}
    if user_ids:
        users_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        user_map = {u.id: u for u in users_result.scalars().all()}

    ai_map = {}
    if ai_ids:
        ais_result = await db.execute(select(AIPersona).where(AIPersona.id.in_(ai_ids)))
        ai_map = {a.id: a for a in ais_result.scalars().all()}

    out = []
    for c in comments:
        if c.is_ai_reply and c.ai_id:
            persona = ai_map.get(c.ai_id)
            author_name = persona.name if persona else "AI"
            author_avatar = persona.avatar_url if persona else ""
        else:
            user = user_map.get(c.user_id)
            author_name = user.nickname if user else "User"
            author_avatar = ""
        out.append(CommentOut(
            id=c.id,
            post_id=c.post_id,
            user_id=c.user_id,
            ai_id=c.ai_id,
            is_ai_reply=bool(c.is_ai_reply),
            reply_to=c.reply_to,
            content=c.content,
            author_name=author_name,
            author_avatar=author_avatar,
            created_at=c.created_at.isoformat(),
        ))
    return out


@router.post("/posts/{post_id}/comments", response_model=CommentOut)
async def create_comment(
    post_id: int,
    body: CommentIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a user comment and schedule a delayed AI reply."""
    # Verify post exists
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")

    # Save user comment
    comment = Comment(
        post_id=post_id,
        user_id=current_user.id,
        ai_id=None,
        is_ai_reply=0,
        reply_to=None,
        content=content,
    )
    db.add(comment)

    # Update intimacy: +0.3 per comment
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id == post.ai_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    if interaction:
        interaction.intimacy_score = min(interaction.intimacy_score + 0.3, 10.0)
    else:
        interaction = Interaction(
            user_id=current_user.id,
            ai_id=post.ai_id,
            intimacy_score=0.3,
        )
        db.add(interaction)

    await db.commit()
    await db.refresh(comment)

    # Fire delayed AI reply task (1-5 min random delay)
    asyncio.create_task(
        _delayed_ai_reply(
            comment_id=comment.id,
            post_id=post_id,
            ai_id=post.ai_id,
            user_id=current_user.id,
            user_nickname=current_user.nickname,
            user_comment=content,
            post_caption=post.caption,
        )
    )

    return CommentOut(
        id=comment.id,
        post_id=comment.post_id,
        user_id=comment.user_id,
        ai_id=comment.ai_id,
        is_ai_reply=False,
        reply_to=comment.reply_to,
        content=comment.content,
        author_name=current_user.nickname,
        author_avatar="",
        created_at=comment.created_at.isoformat(),
    )


async def _delayed_ai_reply(
    comment_id: int,
    post_id: int,
    ai_id: int,
    user_id: int,
    user_nickname: str,
    user_comment: str,
    post_caption: str,
):
    """Background task: wait 1-5 minutes, then generate and save an AI reply."""
    delay = random.randint(60, 300)
    print(f"[comment-reply] Scheduled AI reply for comment {comment_id} in {delay}s")
    await asyncio.sleep(delay)

    try:
        async with async_session() as db:
            # Load persona
            persona_result = await db.execute(select(AIPersona).where(AIPersona.id == ai_id))
            persona = persona_result.scalar_one_or_none()
            if not persona:
                print(f"[comment-reply] AI persona {ai_id} not found, skipping.")
                return

            # Load intimacy + nickname
            interaction_result = await db.execute(
                select(Interaction).where(
                    Interaction.user_id == user_id,
                    Interaction.ai_id == ai_id,
                )
            )
            interaction = interaction_result.scalar_one_or_none()
            intimacy = interaction.intimacy_score if interaction else 0.0
            special_nickname = (interaction.special_nickname or "") if interaction else ""

            # Load memories
            memories = await memory_service.get_contextual_memories(
                user_id=user_id,
                ai_id=ai_id,
                query_text=user_comment,
                intimacy=intimacy,
                top_k=3,
            )
            memories_block = memory_service.format_memories_for_prompt(memories)

            # Generate reply
            print(f"[comment-reply] Generating reply for comment {comment_id}...")
            reply_text = await generate_comment_reply(
                persona_prompt=persona.personality_prompt,
                intimacy=intimacy,
                user_nickname=user_nickname,
                user_comment=user_comment,
                post_caption=post_caption,
                memories_block=memories_block,
                special_nickname=special_nickname,
            )

            # Save AI reply
            ai_comment = Comment(
                post_id=post_id,
                user_id=None,
                ai_id=ai_id,
                is_ai_reply=1,
                reply_to=comment_id,
                content=reply_text,
            )
            db.add(ai_comment)
            await db.commit()
            print(f"[comment-reply] AI replied to comment {comment_id}: {reply_text[:80]}")

    except Exception as e:
        import traceback
        print(f"[comment-reply] Failed for comment {comment_id}: {e}")
        traceback.print_exc()
