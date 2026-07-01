"""
信息流端点模块

================================================================================
功能概述
================================================================================
本模块提供 Instagram 风格的信息流相关 REST API 端点：
- 帖子信息流：获取 AI 人格发布的帖子列表
- 帖子详情：获取单个帖子的详细信息
- 点赞/取消点赞：对帖子进行点赞操作
- 收藏/取消收藏：保存帖子到个人收藏
- Story 查看：获取和标记 Story
- 评论系统：获取评论、发表评论、AI 回复评论

================================================================================
设计理念
================================================================================
1. 亲密度门控：
   - 密友（close_friend）帖子只对亲密度 >= 6 的用户可见
   - 点赞和评论会提升与 AI 的亲密度

2. 批量加载优化：
   - 使用 IN 查询批量加载用户的交互状态
   - 避免 N+1 查询问题

3. 延迟 AI 回复：
   - 用户评论后，AI 会延迟 1-5 分钟再回复
   - 模拟真实的社交媒体交互体验

================================================================================
API 端点列表
================================================================================
GET    /api/feed/posts              - 获取帖子信息流
GET    /api/feed/posts/{post_id}    - 获取单个帖子详情
POST   /api/feed/posts/{post_id}/like    - 点赞帖子
DELETE /api/feed/posts/{post_id}/like    - 取消点赞
POST   /api/feed/posts/{post_id}/save    - 收藏帖子
DELETE /api/feed/posts/{post_id}/save    - 取消收藏
GET    /api/feed/saved              - 获取收藏的帖子
GET    /api/feed/stories            - 获取 Story 列表
POST   /api/feed/stories/{story_id}/view - 标记 Story 已查看
GET    /api/feed/image-proxy        - 图片代理（解决跨域）
GET    /api/feed/posts/{post_id}/comments - 获取评论列表
POST   /api/feed/posts/{post_id}/comments - 发表评论
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete as sql_delete, update as sql_update
from datetime import datetime, timezone, timedelta
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
from models.emotion_state import EmotionState
from services import memory_service, emotion_engine, anchor_service, embedding_service
from services.aliyun_ai_service import generate_comment_reply
from services.emotion_visual_mapper import compute_emotion_visual

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feed", tags=["feed"])


# ── 亲密度延迟回复配置 ────────────────────────────────────
# 亲密度层级 → 延迟秒数范围 (min, max)
# 层级越高（越亲密），延迟越短，模拟真人对不同关系回复速度的差异
REPLY_DELAY_RANGES = {
    0: (60, 300),    # 陌生人 (intimacy 0-2):   1-5 分钟
    1: (60, 180),    # 熟人   (intimacy 2-4):   1-3 分钟
    2: (30, 90),     # 朋友   (intimacy 4-6):   30秒-1.5分钟
    3: (15, 60),     # 挚友   (intimacy 6-7.5): 15秒-1分钟
    4: (10, 45),     # 密友   (intimacy 7.5-9): 10-45秒
    5: (5, 30),      # 灵魂伴侣 (intimacy 9+):  5-30秒
}


def _intimacy_to_tier(intimacy_score: float) -> int:
    """
    将亲密度评分（0-10）映射为延迟回复层级（0-5）。

    Args:
        intimacy_score: 亲密度评分（0-10 浮点数）

    Returns:
        int: 延迟回复层级（0=陌生人，5=灵魂伴侣）
    """
    if intimacy_score < 2.0:
        return 0  # 陌生人
    elif intimacy_score < 4.0:
        return 1  # 熟人
    elif intimacy_score < 6.0:
        return 2  # 朋友
    elif intimacy_score < 7.5:
        return 3  # 挚友
    elif intimacy_score < 9.0:
        return 4  # 密友
    else:
        return 5  # 灵魂伴侣


def calculate_reply_delay(intimacy_tier: int) -> int:
    """
    根据亲密度层级计算 AI 回复延迟秒数。

    层级越高延迟越短，模拟真人对亲密关系回复更快的行为模式。

    Args:
        intimacy_tier: 亲密度层级（0-5）

    Returns:
        int: 延迟秒数
    """
    min_s, max_s = REPLY_DELAY_RANGES.get(intimacy_tier, (60, 300))
    return random.randint(min_s, max_s)


# ── Pydantic 数据模型 ────────────────────────────────────

class EmotionVisualBrief(BaseModel):
    """头像边框视觉参数（精简版，嵌入在帖子/角色信息中返回）。"""
    border_hue: int
    border_saturation: int
    border_brightness: int
    glow_intensity: int
    shimmer_type: str
    mood_label: str


class PostOut(BaseModel):
    """
    帖子输出模型。

    Attributes:
        id: 帖子 ID
        ai_id: AI 人格 ID
        ai_name: AI 人格名称
        ai_avatar: AI 人格头像 URL
        media_url: 媒体（图片/视频）URL
        caption: 帖子文案
        like_count: 点赞数
        is_close_friend: 是否为密友可见帖子
        is_liked: 当前用户是否已点赞
        is_saved: 当前用户是否已收藏
        emotion_visual: 情绪头像边框视觉参数
        created_at: 创建时间
    """
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
    emotion_visual: Optional[EmotionVisualBrief] = None
    created_at: str


# ── 帖子信息流 ────────────────────────────────────────────

@router.get("/posts", response_model=list[PostOut])
async def get_posts(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取 Instagram 风格的帖子信息流。

    返回所有 AI 人格发布的帖子，包含点赞和收藏状态。
    密友可见的帖子只对亲密度 >= 6 的用户显示。

    Args:
        limit: 返回数量上限（默认 20）
        offset: 偏移量（用于分页）
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        list[PostOut]: 帖子列表
    """
    result = await db.execute(
        select(Post, AIPersona)
        .join(AIPersona, Post.ai_id == AIPersona.id)
        .where(Post.status == 1)
        .order_by(Post.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.all()

    # 批量加载用户的交互记录，用于亲密度过滤
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

    # 批量加载用户与各角色的情绪状态，用于头像边框视觉参数
    emotion_visual_map: dict[int, EmotionVisualBrief] = {}
    if ai_ids:
        emo_result = await db.execute(
            select(EmotionState).where(
                EmotionState.user_id == current_user.id,
                EmotionState.ai_id.in_(ai_ids),
            )
        )
        for emo in emo_result.scalars().all():
            visual = compute_emotion_visual(
                emo.energy, emo.pleasure, emo.activation, emo.longing, emo.security,
            )
            emotion_visual_map[emo.ai_id] = EmotionVisualBrief(**visual)

    # 批量加载用户的点赞和收藏状态
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

    # 过滤：排除亲密度 < 6 的用户无法看到的密友帖子
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
            emotion_visual=emotion_visual_map.get(post.ai_id),
            created_at=to_utc_iso(post.created_at),
        )
        for post, persona in filtered
    ]


# ── 单个帖子详情 ─────────────────────────────────────────

@router.get("/posts/{post_id}", response_model=PostOut)
async def get_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取单个帖子的详细信息。

    Args:
        post_id: 帖子 ID
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        PostOut: 帖子详情

    Raises:
        HTTPException: 帖子不存在时返回 404 错误
    """
    result = await db.execute(
        select(Post, AIPersona)
        .join(AIPersona, Post.ai_id == AIPersona.id)
        .where(Post.id == post_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Post not found")
    post, persona = row

    # 检查点赞和收藏状态
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

    # 获取该角色的情绪视觉参数
    emo_result = await db.execute(
        select(EmotionState).where(
            EmotionState.user_id == current_user.id,
            EmotionState.ai_id == post.ai_id,
        )
    )
    emo_state = emo_result.scalar_one_or_none()
    emotion_vis = None
    if emo_state:
        visual = compute_emotion_visual(
            emo_state.energy, emo_state.pleasure, emo_state.activation,
            emo_state.longing, emo_state.security,
        )
        emotion_vis = EmotionVisualBrief(**visual)

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
        emotion_visual=emotion_vis,
        created_at=to_utc_iso(post.created_at),
    )


# ── 点赞/取消点赞（幂等操作）──────────────────────────

@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    点赞帖子（幂等操作）。

    如果已点赞则不重复操作。点赞会提升与 AI 的亲密度（+0.5）。

    Args:
        post_id: 帖子 ID
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 点赞状态和点赞数

    Raises:
        HTTPException: 帖子不存在时返回 404 错误
    """
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # 检查是否已点赞
    existing = await db.execute(
        select(UserLike).where(
            UserLike.user_id == current_user.id,
            UserLike.post_id == post_id,
        )
    )
    if existing.scalar_one_or_none():
        # 已点赞，返回幂等响应
        return {"status": "already_liked", "like_count": post.like_count}

    # 创建点赞记录
    db.add(UserLike(user_id=current_user.id, post_id=post_id))

    # 原子性地增加点赞数
    await db.execute(
        sql_update(Post)
        .where(Post.id == post_id)
        .values(like_count=Post.like_count + 1)
    )

    # 更新亲密度
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

    # 情绪：应用点赞效果
    emo = await emotion_engine.get_or_create(db, current_user.id, post.ai_id)
    emotion_engine.apply_interaction(emo, "like")

    await db.commit()

    # 重新获取更新后的点赞数
    await db.refresh(post)
    return {"status": "liked", "like_count": post.like_count}


@router.delete("/posts/{post_id}/like")
async def unlike_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取消点赞帖子。

    Args:
        post_id: 帖子 ID
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 点赞状态和点赞数

    Raises:
        HTTPException: 帖子不存在时返回 404 错误
    """
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
        # 未点赞，返回幂等响应
        return {"status": "not_liked", "like_count": post.like_count}

    # 删除点赞记录
    await db.delete(like)

    # 原子性地减少点赞数（确保不低于0）
    await db.execute(
        sql_update(Post)
        .where(Post.id == post_id)
        .values(like_count=func.max(Post.like_count - 1, 0))
    )

    await db.commit()

    # 重新获取更新后的点赞数
    await db.refresh(post)
    return {"status": "unliked", "like_count": post.like_count}


# ── 收藏/取消收藏 ───────────────────────────────────────

@router.post("/posts/{post_id}/save")
async def save_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    收藏帖子。

    Args:
        post_id: 帖子 ID
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 收藏状态

    Raises:
        HTTPException: 帖子不存在时返回 404 错误
    """
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
    """
    取消收藏帖子。

    Args:
        post_id: 帖子 ID
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 收藏状态
    """
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
    """
    获取用户收藏的帖子列表。

    Args:
        limit: 返回数量上限（默认 20）
        offset: 偏移量（用于分页）
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        list[PostOut]: 收藏的帖子列表
    """
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

    # 批量加载情绪视觉参数
    saved_ai_ids = list({post.ai_id for post, _, _ in rows})
    saved_emo_visual: dict[int, EmotionVisualBrief] = {}
    if saved_ai_ids:
        emo_result = await db.execute(
            select(EmotionState).where(
                EmotionState.user_id == current_user.id,
                EmotionState.ai_id.in_(saved_ai_ids),
            )
        )
        for emo in emo_result.scalars().all():
            visual = compute_emotion_visual(
                emo.energy, emo.pleasure, emo.activation, emo.longing, emo.security,
            )
            saved_emo_visual[emo.ai_id] = EmotionVisualBrief(**visual)

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
            emotion_visual=saved_emo_visual.get(post.ai_id),
            created_at=to_utc_iso(post.created_at),
        )
        for post, persona, _ in rows
    ]


# ── Story 查看 ─────────────────────────────────────────────────

@router.post("/stories/{story_id}/view")
async def mark_story_viewed(
    story_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    标记 Story 为已查看。

    Args:
        story_id: Story ID
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 查看状态
    """
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


# ── 图片代理 ─────────────────────────────────────────────────

@router.get("/image-proxy")
async def image_proxy(url: str = Query(...)):
    """
    图片代理端点。

    用于解决 Flutter Web 中的跨域图片加载问题。
    只代理 HTTPS URL，返回带缓存的图片响应。

    Args:
        url: 图片 URL（必须是 HTTPS）

    Returns:
        StreamingResponse: 图片响应

    Raises:
        HTTPException: URL 无效时返回 400 错误
    """
    if not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL")
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/png")
        return StreamingResponse(
            iter([resp.content]),
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},  # 缓存 24 小时
        )


# ── Story 数据模型 ─────────────────────────────────────────────────────

class StoryOut(BaseModel):
    """
    Story 输出模型。

    Attributes:
        id: Story ID
        ai_id: AI 人格 ID
        ai_name: AI 人格名称
        ai_avatar: AI 人格头像 URL
        video_url: 视频 URL
        caption: Story 文案
        is_viewed: 当前用户是否已查看
        created_at: 创建时间
        expires_at: 过期时间
    """
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
    """
    获取未过期的 Story 列表。

    只返回过期时间晚于当前时间的 Story。

    Args:
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        list[StoryOut]: Story 列表
    """
    result = await db.execute(
        select(Story, AIPersona)
        .join(AIPersona, Story.ai_id == AIPersona.id)
        .order_by(Story.created_at.desc())
    )
    rows = result.all()

    # 过滤掉已过期的 Story
    now = datetime.now(timezone.utc)
    valid_stories = [
        (story, persona) for story, persona in rows
        if story.expires_at.astimezone(timezone.utc) > now
    ]

    # 批量加载查看状态
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


# ── 评论系统 ──────────────────────────────────────────────

class CommentIn(BaseModel):
    """评论输入模型。"""
    content: str


class AiReplyStatus(BaseModel):
    """
    AI 回复状态子模型。

    status:
        - "pending":   AI 已看到评论，回复尚未生成
        - "delivered": AI 回复已生成并展示
        - "none":      该评论不需要 AI 回复（AI 发的评论或无需回复的场景）

    Attributes:
        status: 回复状态（pending / delivered / none）
        text: AI 回复文本（delivered 时有值）
        estimated_at: 预计回复时间（pending 时有值，ISO-8601 格式）
        delivered_at: 实际回复时间（delivered 时有值，ISO-8601 格式）
    """
    status: str  # "pending" | "delivered" | "none"
    text: Optional[str] = None
    estimated_at: Optional[str] = None
    delivered_at: Optional[str] = None


class CommentOut(BaseModel):
    """
    评论输出模型。

    Attributes:
        id: 评论 ID
        post_id: 帖子 ID
        user_id: 用户 ID（AI 回复时为 None）
        ai_id: AI 人格 ID（用户评论时为 None）
        is_ai_reply: 是否为 AI 回复
        reply_to: 回复的评论 ID
        content: 评论内容
        author_name: 作者名称
        author_avatar: 作者头像
        ai_seen: AI 是否已看到该评论
        ai_reply: AI 回复状态（仅用户评论时有效）
        created_at: 创建时间
    """
    id: int
    post_id: int
    user_id: Optional[int]
    ai_id: Optional[int]
    is_ai_reply: bool
    reply_to: Optional[int]
    content: str
    author_name: str
    author_avatar: str
    ai_seen: bool = False
    ai_reply: Optional[AiReplyStatus] = None
    created_at: str


@router.get("/posts/{post_id}/comments", response_model=list[CommentOut])
async def get_comments(
    post_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取帖子的评论列表（分页）。

    每条评论包含 ai_reply 状态对象：
    - pending:   AI 已看到但尚未回复，附带预计回复时间
    - delivered: AI 回复已生成，附带回复文本和时间
    - none:      AI 评论或无需回复的场景

    Args:
        post_id: 帖子 ID
        limit: 返回数量上限（默认 50）
        offset: 偏移量
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        list[CommentOut]: 评论列表
    """
    result = await db.execute(
        select(Comment)
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
        .offset(offset)
        .limit(limit)
    )
    comments = result.scalars().all()

    # 批量加载用户和 AI 信息
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

    # 批量查询 AI 回复评论：找到所有 reply_to 指向当前评论列表的 AI 回复
    comment_ids = [c.id for c in comments]
    ai_reply_map: dict[int, Comment] = {}  # parent_comment_id -> AI reply Comment
    if comment_ids:
        ai_replies_result = await db.execute(
            select(Comment).where(
                Comment.post_id == post_id,
                Comment.is_ai_reply == 1,
                Comment.reply_to.in_(comment_ids),
            )
        )
        for ai_reply in ai_replies_result.scalars().all():
            if ai_reply.reply_to is not None:
                ai_reply_map[ai_reply.reply_to] = ai_reply

    # 确保 AI 回复评论的作者信息也被加载
    for ai_reply in ai_reply_map.values():
        if ai_reply.ai_id and ai_reply.ai_id not in ai_map:
            ais_result = await db.execute(
                select(AIPersona).where(AIPersona.id == ai_reply.ai_id)
            )
            persona = ais_result.scalar_one_or_none()
            if persona:
                ai_map[persona.id] = persona

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

        # 构建 ai_reply 状态
        ai_reply_status: Optional[AiReplyStatus] = None
        if not c.is_ai_reply and c.user_id:
            # 这是用户评论，检查是否有 AI 回复
            ai_reply_comment = ai_reply_map.get(c.id)
            if ai_reply_comment:
                # AI 回复已生成
                ai_reply_status = AiReplyStatus(
                    status="delivered",
                    text=ai_reply_comment.content,
                    delivered_at=to_utc_iso(ai_reply_comment.created_at),
                )
            elif c.ai_seen and c.ai_reply_at:
                # AI 已看到但尚未回复
                ai_reply_status = AiReplyStatus(
                    status="pending",
                    text=None,
                    estimated_at=to_utc_iso(c.ai_reply_at),
                )
            else:
                # 兜底：旧数据无 ai_seen 标记
                ai_reply_status = AiReplyStatus(status="none")
        elif c.is_ai_reply:
            # AI 回复评论本身不需要 ai_reply 状态
            ai_reply_status = None

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
            ai_seen=bool(c.ai_seen),
            ai_reply=ai_reply_status,
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
    """
    发表评论并安排基于亲密度的延迟 AI 回复。

    用户发表评论后：
    1. 立即标记 ai_seen=True、ai_seen_at=NOW()
    2. 根据用户与该 AI 的亲密度层级计算延迟时间
    3. 计算 ai_reply_at=NOW()+delay 并持久化到 DB
    4. 启动后台延迟任务，到期后生成 AI 回复

    Args:
        post_id: 帖子 ID
        body: 评论输入
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        CommentOut: 新创建的评论（含 ai_reply 预计状态）

    Raises:
        HTTPException: 帖子不存在或评论为空时返回错误
    """
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")

    # 查询亲密度，计算延迟回复时间
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == current_user.id,
            Interaction.ai_id == post.ai_id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    intimacy_score = interaction.intimacy_score if interaction else 0.0
    intimacy_tier = _intimacy_to_tier(intimacy_score)
    delay_seconds = calculate_reply_delay(intimacy_tier)

    now = datetime.now(timezone.utc)
    reply_at = now + timedelta(seconds=delay_seconds)

    # 创建评论，立即标记 AI 已看到并记录计划回复时间
    comment = Comment(
        post_id=post_id,
        user_id=current_user.id,
        ai_id=None,
        is_ai_reply=0,
        reply_to=None,
        content=content,
        ai_seen=True,
        ai_seen_at=now,
        ai_reply_at=reply_at,
    )
    db.add(comment)

    # 更新亲密度
    if interaction:
        interaction.intimacy_score = min(interaction.intimacy_score + 0.3, 10.0)
    else:
        interaction = Interaction(
            user_id=current_user.id,
            ai_id=post.ai_id,
            intimacy_score=0.3,
        )
        db.add(interaction)

    # 应用评论的情绪效果
    emo = await emotion_engine.get_or_create(db, current_user.id, post.ai_id)
    emotion_engine.apply_interaction(emo, "comment")

    await db.commit()
    await db.refresh(comment)

    # 安排基于亲密度层级的延迟 AI 回复后台任务
    asyncio.create_task(
        _delayed_ai_reply(
            comment_id=comment.id,
            post_id=post_id,
            ai_id=post.ai_id,
            user_id=current_user.id,
            user_nickname=current_user.nickname,
            user_comment=content,
            post_caption=post.caption,
            delay_seconds=delay_seconds,
        )
    )

    logger.info(
        "[comment-reply] User %d commented on post %d, AI reply scheduled in %ds (tier=%d, intimacy=%.1f)",
        current_user.id, post_id, delay_seconds, intimacy_tier, intimacy_score,
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
        ai_seen=True,
        ai_reply=AiReplyStatus(
            status="pending",
            text=None,
            estimated_at=to_utc_iso(reply_at),
        ),
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
    delay_seconds: int,
):
    """
    后台任务：等待指定秒数后生成并保存 AI 回复。

    延迟时间由调用方根据亲密度层级计算并传入。
    ai_reply_at 已在评论创建时持久化到 DB，前端可据此轮询。
    回复生成时会考虑用户的亲密度、记忆和情绪状态。

    Args:
        comment_id: 原评论 ID
        post_id: 帖子 ID
        ai_id: AI 人格 ID
        user_id: 用户 ID
        user_nickname: 用户昵称
        user_comment: 用户评论内容
        post_caption: 帖子文案
        delay_seconds: 延迟秒数（由 calculate_reply_delay 计算）
    """
    logger.info("[comment-reply] Scheduled AI reply for comment %d in %ds", comment_id, delay_seconds)
    await asyncio.sleep(delay_seconds)

    try:
        async with async_session() as db:
            # 获取 AI 人格信息
            persona_result = await db.execute(select(AIPersona).where(AIPersona.id == ai_id))
            persona = persona_result.scalar_one_or_none()
            if not persona:
                return

            # 获取用户与 AI 的交互信息
            interaction_result = await db.execute(
                select(Interaction).where(
                    Interaction.user_id == user_id,
                    Interaction.ai_id == ai_id,
                )
            )
            interaction = interaction_result.scalar_one_or_none()
            intimacy = interaction.intimacy_score if interaction else 0.0
            special_nickname = (interaction.special_nickname or "") if interaction else ""

            # 获取评论的嵌入向量
            comment_embedding = None
            try:
                comment_embedding = await embedding_service.get_embedding(user_comment)
            except Exception:
                pass

            # 获取相关记忆
            memories = await memory_service.get_contextual_memories(
                user_id=user_id,
                ai_id=ai_id,
                query_text=user_comment,
                intimacy=intimacy,
                top_k=3,
                precomputed_embedding=comment_embedding,
            )
            memories_block = memory_service.format_memories_for_prompt(memories)

            # 检测活跃锚点
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

            # 获取情绪状态
            emo = await emotion_engine.get_or_create(db, user_id, ai_id)
            emo_directive = emotion_engine.build_emotion_directive(emo)
            emo_overrides = emotion_engine.get_param_overrides(emo)

            # 生成 AI 回复
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
                timezone_str=persona.timezone,
            )

            # 应用聊天情绪效果
            emotion_engine.apply_interaction(emo, "chat")

            # 提取和存储锚点
            asyncio.create_task(
                anchor_service.extract_and_store_anchors(
                    user_id=user_id,
                    ai_id=ai_id,
                    user_message=user_comment,
                    ai_reply=reply_text,
                )
            )

            # 创建 AI 回复评论
            ai_comment = Comment(
                post_id=post_id,
                user_id=None,
                ai_id=ai_id,
                is_ai_reply=1,
                reply_to=comment_id,
                content=reply_text,
            )
            db.add(ai_comment)

            # 发送评论回复通知
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