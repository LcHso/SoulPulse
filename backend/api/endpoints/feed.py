from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sql_delete
from datetime import datetime, timezone
from typing import Optional
import asyncio
import random
import logging
import httpx

from core.utils import to_utc_iso

from core.database import get_db, async_session
from core.security import get_current_user
from models.user import User
from models.post import Post
from models.ai_persona import AIPersona
from models.interaction import Interaction
from models.story import Story
from models.comment import Comment
from models.user_like import UserLike
from models.saved_post import SavedPost
from models.story_view import StoryView
from models.notification import Notification
from services import memory_service, emotion_engine, anchor_service, embedding_service
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
    is_liked: bool = False
    is_saved: bool = False
    created_at: str


@router.get("/posts", response_model=list[PostOut])
async def get_posts(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch the Ins-style feed of posts with like/save status."""
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

    # Batch-load user's likes and saves
    post_ids = [post.id for post, _ in rows]
    liked_ids = set()
    saved_ids = set()
    if post_ids:
        likes_result = await db.execute(
            select(UserLike.post_id).where(
                UserLike.user_id == current_user.id,
                UserLike.post_id.in_(post_ids),
            )
        )
        liked_ids = {row[0] for row in likes_result.all()}

        saves_result = await db.execute(
            select(SavedPost.post_id).where(
                SavedPost.user_id == current_user.id,
                SavedPost.post_id.in_(post_ids),
            )
        )
        saved_ids = {row[0] for row in saves_result.all()}

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
            is_liked=post.id in liked_ids,
            is_saved=post.id in saved_ids,
            created_at=to_utc_iso(post.created_at),
        )
        for post, persona in filtered
    ]


# ── Single post detail ─────────────────────────────────────────

@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single post by ID."""
    result = await db.execute(
        select(Post, AIPersona)
        .join(AIPersona, Post.ai_id == AIPersona.id)
        .where(Post.id == post_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    post, persona = row

    # Check like/save status
    liked_result = await db.execute(
        select(UserLike.id).where(
            UserLike.user_id == current_user.id,
            UserLike.post_id == post_id,
        )
    )
    is_liked = liked_result.scalar_one_or_none() is not None

    saved_result = await db.execute(
        select(SavedPost.id).where(
            SavedPost.user_id == current_user.id,
            SavedPost.post_id == post_id,
        )
    )
    is_saved = saved_result.scalar_one_or_none() is not None

    return PostOut(
        id=post.id,
        ai_id=persona.id,
        ai_name=persona.name,
        ai_avatar=persona.avatar_url,
        media_url=post.media_url,
        caption=post.caption,
        like_count=post.like_count,
        is_close_friend=post.is_close_friend,
        is_liked=is_liked,
        is_saved=is_saved,
        created_at=to_utc_iso(post.created_at),
    )


# ── Like / Unlike (idempotent) ──────────────────────────────────

@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Like a post (idempotent). Returns current like state and count."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # Check if already liked
    existing = await db.execute(
        select(UserLike).where(
            UserLike.user_id == current_user.id,
            UserLike.post_id == post_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"liked": True, "like_count": post.like_count}

    # Create like record
    db.add(UserLike(user_id=current_user.id, post_id=post_id))
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
        interaction.intimacy_score = min(interaction.intimacy_score + 0.5, 10.0)
    else:
        interaction = Interaction(
            user_id=current_user.id,
            ai_id=post.ai_id,
            intimacy_score=0.5,
        )
        db.add(interaction)

    # Emotion: apply "like" effect
    emo = await emotion_engine.get_or_create(db, current_user.id, post.ai_id)
    emotion_engine.apply_interaction(emo, "like")

    await db.commit()
    return {"liked": True, "like_count": post.like_count}


@router.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlike a post."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = await db.execute(
        select(UserLike).where(
            UserLike.user_id == current_user.id,
            UserLike.post_id == post_id,
        )
    )
    like = existing.scalar_one_or_none()
    if not like:
        return {"liked": False, "like_count": post.like_count}

    await db.delete(like)
    post.like_count = max(0, post.like_count - 1)
    await db.commit()
    return {"liked": False, "like_count": post.like_count}


# ── Save / Unsave ───────────────────────────────────────────────

@router.post("/posts/{post_id}/save")
async def save_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save/bookmark a post."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Post not found")

    existing = await db.execute(
        select(SavedPost).where(
            SavedPost.user_id == current_user.id,
            SavedPost.post_id == post_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"saved": True}

    db.add(SavedPost(user_id=current_user.id, post_id=post_id))
    await db.commit()
    return {"saved": True}


@router.delete("/posts/{post_id}/save")
async def unsave_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove saved post."""
    existing = await db.execute(
        select(SavedPost).where(
            SavedPost.user_id == current_user.id,
            SavedPost.post_id == post_id,
        )
    )
    saved = existing.scalar_one_or_none()
    if saved:
        await db.delete(saved)
        await db.commit()
    return {"saved": False}


@router.get("/saved", response_model=list[PostOut])
async def get_saved_posts(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get user's saved posts."""
    result = await db.execute(
        select(Post, AIPersona, SavedPost)
        .join(AIPersona, Post.ai_id == AIPersona.id)
        .join(SavedPost, SavedPost.post_id == Post.id)
        .where(SavedPost.user_id == current_user.id)
        .order_by(SavedPost.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    post_ids = [post.id for post, _, _ in rows]
    liked_ids = set()
    if post_ids:
        likes_result = await db.execute(
            select(UserLike.post_id).where(
                UserLike.user_id == current_user.id,
                UserLike.post_id.in_(post_ids),
            )
        )
        liked_ids = {row[0] for row in likes_result.all()}

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
            is_liked=post.id in liked_ids,
            is_saved=True,
            created_at=to_utc_iso(post.created_at),
        )
        for post, persona, _ in rows
    ]


# ── Story views ─────────────────────────────────────────────────

@router.post("/stories/{story_id}/view")
async def mark_story_viewed(
    story_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a story as viewed by the user."""
    existing = await db.execute(
        select(StoryView).where(
            StoryView.user_id == current_user.id,
            StoryView.story_id == story_id,
        )
    )
    if not existing.scalar_one_or_none():
        db.add(StoryView(user_id=current_user.id, story_id=story_id))
        await db.commit()
    return {"viewed": True}


# ── Image proxy ─────────────────────────────────────────────────

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


# ── Stories ─────────────────────────────────────────────────────

class StoryOut(BaseModel):
    id: int
    ai_id: int
    ai_name: str
    ai_avatar: str
    video_url: str
    caption: str
    is_viewed: bool = False
    created_at: str
    expires_at: str


@router.get("/stories", response_model=list[StoryOut])
async def get_stories(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch unexpired stories with AI persona info and view status."""
    result = await db.execute(
        select(Story, AIPersona)
        .join(AIPersona, Story.ai_id == AIPersona.id)
        .order_by(Story.created_at.desc())
    )
    rows = result.all()

    now = datetime.now(timezone.utc)
    valid_stories = [
        (story, persona) for story, persona in rows
        if story.expires_at.astimezone(timezone.utc) > now
    ]

    # Batch-load view status
    story_ids = [story.id for story, _ in valid_stories]
    viewed_ids = set()
    if story_ids:
        views_result = await db.execute(
            select(StoryView.story_id).where(
                StoryView.user_id == current_user.id,
                StoryView.story_id.in_(story_ids),
            )
        )
        viewed_ids = {row[0] for row in views_result.all()}

    return [
        StoryOut(
            id=story.id,
            ai_id=story.ai_id,
            ai_name=persona.name,
            ai_avatar=persona.avatar_url,
            video_url=story.video_url,
            caption=story.caption,
            is_viewed=story.id in viewed_ids,
            created_at=to_utc_iso(story.created_at),
            expires_at=to_utc_iso(story.expires_at),
        )
        for story, persona in valid_stories
    ]


# ── Comment system ──────────────────────────────────────────────

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
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch paginated comments for a post."""
    result = await db.execute(
        select(Comment)
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    comments = result.scalars().all()

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
            author_avatar = user.avatar_url or "" if user else ""
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
            created_at=to_utc_iso(c.created_at),
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
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")

    comment = Comment(
        post_id=post_id,
        user_id=current_user.id,
        ai_id=None,
        is_ai_reply=0,
        reply_to=None,
        content=content,
    )
    db.add(comment)

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

    emo = await emotion_engine.get_or_create(db, current_user.id, post.ai_id)
    emotion_engine.apply_interaction(emo, "comment")

    await db.commit()
    await db.refresh(comment)

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
        author_avatar=current_user.avatar_url or "",
        created_at=to_utc_iso(comment.created_at),
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
    logger.info("[comment-reply] Scheduled AI reply for comment %d in %ds", comment_id, delay)
    await asyncio.sleep(delay)

    try:
        async with async_session() as db:
            persona_result = await db.execute(select(AIPersona).where(AIPersona.id == ai_id))
            persona = persona_result.scalar_one_or_none()
            if not persona:
                return

            interaction_result = await db.execute(
                select(Interaction).where(
                    Interaction.user_id == user_id,
                    Interaction.ai_id == ai_id,
                )
            )
            interaction = interaction_result.scalar_one_or_none()
            intimacy = interaction.intimacy_score if interaction else 0.0
            special_nickname = (interaction.special_nickname or "") if interaction else ""

            comment_embedding = None
            try:
                comment_embedding = await embedding_service.get_embedding(user_comment)
            except Exception:
                pass

            memories = await memory_service.get_contextual_memories(
                user_id=user_id,
                ai_id=ai_id,
                query_text=user_comment,
                intimacy=intimacy,
                top_k=3,
                precomputed_embedding=comment_embedding,
            )
            memories_block = memory_service.format_memories_for_prompt(memories)

            anchor_dirs = ""
            try:
                all_anchors = await anchor_service.load_anchors(db, user_id, ai_id)
                if all_anchors and comment_embedding:
                    active = await anchor_service.detect_active_anchors(
                        all_anchors, comment_embedding, user_id, ai_id,
                    )
                    sentiment = anchor_service.detect_sentiment(user_comment)
                    anchor_dirs = anchor_service.build_anchor_directives(
                        active, all_anchors, sentiment,
                    )
                    if active:
                        asyncio.create_task(
                            anchor_service.increment_hit_counts_bg(
                                user_id, ai_id, [a.id for a in active],
                            )
                        )
            except Exception:
                pass

            emo = await emotion_engine.get_or_create(db, user_id, ai_id)
            emo_directive = emotion_engine.build_emotion_directive(emo)
            emo_overrides = emotion_engine.get_param_overrides(emo)

            reply_text = await generate_comment_reply(
                persona_prompt=persona.personality_prompt,
                intimacy=intimacy,
                user_nickname=user_nickname,
                user_comment=user_comment,
                post_caption=post_caption,
                memories_block=memories_block,
                special_nickname=special_nickname,
                emotion_directive=emo_directive,
                emotion_overrides=emo_overrides,
                anchor_directives=anchor_dirs,
            )

            emotion_engine.apply_interaction(emo, "chat")

            asyncio.create_task(
                anchor_service.extract_and_store_anchors(
                    user_id=user_id,
                    ai_id=ai_id,
                    user_message=user_comment,
                    ai_reply=reply_text,
                )
            )

            ai_comment = Comment(
                post_id=post_id,
                user_id=None,
                ai_id=ai_id,
                is_ai_reply=1,
                reply_to=comment_id,
                content=reply_text,
            )
            db.add(ai_comment)

            # Write notification for comment reply
            notif = Notification(
                user_id=user_id,
                type="comment_reply",
                title=f"{persona.name} replied to your comment",
                body=reply_text[:200],
                data_json=f'{{"post_id": {post_id}, "ai_id": {ai_id}}}',
            )
            db.add(notif)

            await db.commit()
            logger.info("[comment-reply] AI replied to comment %d", comment_id)

    except Exception as e:
        logger.exception("[comment-reply] Failed for comment %d: %s", comment_id, e)
