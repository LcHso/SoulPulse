"""
管理端点模块 - SoulPulse 开发者控制台 (SDC)

================================================================================
功能概述
================================================================================
本模块提供管理员专用的 REST API 端点：
- 待审核帖子管理：审核、拒绝、重新生成帖子
- 分析概览：系统统计数据
- AI 人格管理：查看和管理 AI 人格
- 用户管理：查看用户列表、设置管理员权限

================================================================================
设计理念
================================================================================
1. 管理员验证：
   - 所有端点都要求用户具有管理员权限（is_admin=1）
   - 使用 get_current_admin_user 依赖进行权限验证

2. 帖子审核流程：
   - 状态 0：待审核（pending）
   - 状态 1：已发布（published）
   - 状态 2：已拒绝（rejected）

3. 图像重新生成：
   - 使用 AI 人格的基础面部图像作为参考
   - 保持角色视觉一致性

================================================================================
API 端点列表
================================================================================
GET    /api/admin/posts/pending            - 获取待审核帖子列表
POST   /api/admin/posts/{post_id}/approve  - 审核通过帖子
POST   /api/admin/posts/{post_id}/reject   - 拒绝帖子
POST   /api/admin/posts/{post_id}/regenerate - 重新生成帖子图像
GET    /api/admin/analytics/overview       - 获取分析概览
GET    /api/admin/personas                 - 获取 AI 人格列表
GET    /api/admin/users                    - 获取用户列表
POST   /api/admin/users/{user_id}/set-admin - 设置用户管理员权限
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_admin_user
from models.user import User
from models.post import Post
from models.ai_persona import AIPersona

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ── Pydantic 数据模型 ────────────────────────────────────────────────

class PostOut(BaseModel):
    """
    帖子输出模型（管理视图）。

    Attributes:
        id: 帖子 ID
        ai_id: AI 人格 ID
        ai_name: AI 人格名称
        ai_avatar: AI 人格头像 URL
        media_url: 媒体 URL
        caption: 帖子文案
        status: 帖子状态（0=待审核，1=已发布，2=已拒绝）
        created_at: 创建时间
    """
    id: int
    ai_id: int
    ai_name: str
    ai_avatar: str
    media_url: str
    caption: str
    status: int
    created_at: str

    class Config:
        from_attributes = True


class PendingPostsResponse(BaseModel):
    """
    待审核帖子列表响应模型。

    Attributes:
        posts: 帖子列表
        total: 总数
        has_more: 是否有更多
    """
    posts: list[PostOut]
    total: int
    has_more: bool


class RegenerateRequest(BaseModel):
    """
    重新生成请求模型。

    Attributes:
        new_caption: 新文案（可选，如果为 None 则保持原文案）
    """
    new_caption: str | None = None


class AnalyticsOverview(BaseModel):
    """
    分析概览模型。

    Attributes:
        total_users: 总用户数
        total_personas: 总 AI 人格数
        pending_posts: 待审核帖子数
        published_posts: 已发布帖子数
        total_messages: 总消息数
    """
    total_users: int
    total_personas: int
    pending_posts: int
    published_posts: int
    total_messages: int


class PersonaOut(BaseModel):
    """
    AI 人格输出模型。

    Attributes:
        id: AI 人格 ID
        name: 名称
        bio: 简介
        profession: 职业
        gender_tag: 性别标签
        category: 分类
        archetype: 原型
        base_face_url: 基础面部图像 URL
        visual_prompt_tags: 视觉提示标签
        avatar_url: 头像 URL
        is_active: 是否激活
    """
    id: int
    name: str
    bio: str
    profession: str
    gender_tag: str
    category: str
    archetype: str
    base_face_url: str | None
    visual_prompt_tags: str | None
    avatar_url: str
    is_active: int

    class Config:
        from_attributes = True


class UserOut(BaseModel):
    """
    用户输出模型（管理视图）。

    Attributes:
        id: 用户 ID
        email: 邮箱
        nickname: 昵称
        avatar_url: 头像 URL
        gem_balance: 宝石余额
        is_admin: 是否为管理员
        created_at: 创建时间
    """
    id: int
    email: str
    nickname: str
    avatar_url: str | None
    gem_balance: int
    is_admin: int
    created_at: str

    class Config:
        from_attributes = True


# ── 辅助函数 ─────────────────────────────────────────────────

def _to_utc_iso(dt: datetime) -> str:
    """
    将 datetime 转换为 UTC ISO-8601 字符串（带 Z 后缀）。

    Args:
        dt: datetime 对象

    Returns:
        str: ISO-8601 格式的 UTC 时间字符串
    """
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── 待审核帖子管理 ─────────────────────────────────────────────────

@router.get("/posts/pending", response_model=PendingPostsResponse)
async def list_pending_posts(
    limit: int = 20,
    offset: int = 0,
    ai_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    获取所有待审核帖子列表。

    支持按 AI 人格筛选。返回分页结果。

    Args:
        limit: 返回数量上限（默认 20）
        offset: 偏移量
        ai_id: AI 人格 ID 筛选（可选）
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        PendingPostsResponse: 待审核帖子列表和分页信息
    """
    # 构建查询（带可选筛选条件）
    query = (
        select(Post, AIPersona)
        .join(AIPersona, Post.ai_id == AIPersona.id)
        .where(Post.status == 0)
        .order_by(Post.created_at.desc())
    )
    if ai_id:
        query = query.where(Post.ai_id == ai_id)

    # 获取总数
    count_query = select(func.count(Post.id)).where(Post.status == 0)
    if ai_id:
        count_query = count_query.where(Post.ai_id == ai_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 获取分页结果
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    rows = result.all()

    posts = []
    for post, persona in rows:
        posts.append(PostOut(
            id=post.id,
            ai_id=post.ai_id,
            ai_name=persona.name,
            ai_avatar=persona.avatar_url,
            media_url=post.media_url,
            caption=post.caption,
            status=post.status,
            created_at=_to_utc_iso(post.created_at),
        ))

    return PendingPostsResponse(
        posts=posts,
        total=total,
        has_more=offset + limit < total,
    )


@router.post("/posts/{post_id}/approve")
async def approve_post(
    post_id: int,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    审核通过帖子。

    将帖子状态设置为已发布（status=1），并通知所有关注者。

    Args:
        post_id: 帖子 ID
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        dict: 成功消息和更新后的状态

    Raises:
        HTTPException: 帖子不存在或状态不是待审核时返回错误
    """
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    if post.status != 0:
        raise HTTPException(status_code=400, detail="Post is not pending")

    # 更新状态为已发布
    post.status = 1
    await db.flush()

    # 通知所有关注者有新帖子
    from models.follow import Follow
    from models.notification import Notification

    # 获取 AI 人格信息
    persona_result = await db.execute(
        select(AIPersona).where(AIPersona.id == post.ai_id)
    )
    persona = persona_result.scalar_one_or_none()
    if persona:
        follower_result = await db.execute(
            select(Follow.user_id).where(Follow.ai_id == persona.id)
        )
        for (follower_uid,) in follower_result.all():
            db.add(Notification(
                user_id=follower_uid,
                type="new_post",
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
    admin: User = Depends(get_current_admin_user),
):
    """
    拒绝帖子。

    将帖子状态设置为已拒绝（status=2）。

    Args:
        post_id: 帖子 ID
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        dict: 成功消息和更新后的状态

    Raises:
        HTTPException: 帖子不存在或状态不是待审核时返回错误
    """
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
    admin: User = Depends(get_current_admin_user),
):
    """
    重新生成帖子图像（一键重生成）。

    使用 AI 人格的基础面部图像作为参考，生成新的图像。
    保持帖子状态为待审核（status=0）以便重新审核。

    Args:
        post_id: 帖子 ID
        request: 重新生成请求（可选，包含新文案）
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        dict: 成功消息和新的图像 URL

    Raises:
        HTTPException: 帖子不存在、AI 人格不存在或没有基础面部图像时返回错误
    """
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    # 获取带视觉标识信息的 AI 人格
    persona_result = await db.execute(
        select(AIPersona).where(AIPersona.id == post.ai_id)
    )
    persona = persona_result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    # 检查是否有面部参考图像
    base_face_url = persona.base_face_url
    if not base_face_url:
        raise HTTPException(
            status_code=400,
            detail="Persona has no base_face_url for image generation",
        )

    # 更新文案（如果提供了新文案）
    new_caption = request.new_caption if request else None
    if not new_caption:
        new_caption = post.caption

    # 导入图像生成服务
    from services.image_gen_service import (
        generate_image_with_face_ref,
        download_to_static,
        ENFORCED_NEGATIVE_PROMPT,
        QUALITY_SUFFIX,
    )
    from services.aliyun_ai_service import generate_image_prompt

    try:
        # 生成场景提示词
        img_prompt = await generate_image_prompt(
            persona_prompt=persona.personality_prompt,
            style_tags=persona.ins_style_tags,
            caption=new_caption,
            visual_description=persona.visual_prompt_tags,
        )

        # 使用面部参考生成图像
        urls = await generate_image_with_face_ref(
            prompt=img_prompt,
            face_ref_url=base_face_url,
            size="720*1280",
            n=1,
            persona_id=persona.id,
            negative_prompt=ENFORCED_NEGATIVE_PROMPT,
        )

        if urls:
            # 下载图像到本地静态存储
            new_media_url = await download_to_static(urls[0], prefix=f"regen_{post.id}")
            post.media_url = new_media_url
            post.caption = new_caption
            # 保持状态为待审核以便重新审核
            await db.commit()
            return {
                "message": "Image regenerated",
                "post_id": post_id,
                "media_url": new_media_url,
                "status": 0,
            }
        else:
            raise HTTPException(status_code=500, detail="Image generation failed")

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {str(e)}")


# ── 分析概览 ─────────────────────────────────────────────────────────

@router.get("/analytics/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    获取仪表盘概览统计数据。

    返回用户数、AI 人格数、帖子状态统计和消息数。

    Args:
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        AnalyticsOverview: 统计数据
    """
    # 统计用户数
    users_result = await db.execute(select(func.count(User.id)))
    total_users = users_result.scalar() or 0

    # 统计活跃 AI 人格数
    personas_result = await db.execute(
        select(func.count(AIPersona.id)).where(AIPersona.is_active == 1)
    )
    total_personas = personas_result.scalar() or 0

    # 按状态统计帖子数
    pending_result = await db.execute(
        select(func.count(Post.id)).where(Post.status == 0)
    )
    pending_posts = pending_result.scalar() or 0

    published_result = await db.execute(
        select(func.count(Post.id)).where(Post.status == 1)
    )
    published_posts = published_result.scalar() or 0

    # 统计消息数（近似值）
    from models.chat_message import ChatMessage
    messages_result = await db.execute(select(func.count(ChatMessage.id)))
    total_messages = messages_result.scalar() or 0

    return AnalyticsOverview(
        total_users=total_users,
        total_personas=total_personas,
        pending_posts=pending_posts,
        published_posts=published_posts,
        total_messages=total_messages,
    )


# ── AI 人格管理 ────────────────────────────────────────────────

@router.get("/personas", response_model=list[PersonaOut])
async def list_personas(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    获取所有 AI 人格列表（管理视图）。

    按 sort_order 和 id 排序返回。

    Args:
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        list[PersonaOut]: AI 人格列表
    """
    result = await db.execute(
        select(AIPersona).order_by(AIPersona.sort_order, AIPersona.id)
    )
    personas = result.scalars().all()
    return [
        PersonaOut(
            id=p.id,
            name=p.name,
            bio=p.bio,
            profession=p.profession,
            gender_tag=p.gender_tag,
            category=p.category,
            archetype=p.archetype,
            base_face_url=p.base_face_url,
            visual_prompt_tags=p.visual_prompt_tags,
            avatar_url=p.avatar_url,
            is_active=p.is_active,
        )
        for p in personas
    ]


class PersonaUpdateRequest(BaseModel):
    """
    AI 人格更新请求模型。

    所有字段均为可选，仅更新提供的字段。
    """
    visual_prompt_tags: str | None = None
    base_face_url: str | None = None
    avatar_url: str | None = None
    is_active: int | None = None
    bio: str | None = None
    personality_prompt: str | None = None


@router.put("/personas/{persona_id}", response_model=PersonaOut)
async def update_persona(
    persona_id: int,
    request: PersonaUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    更新 AI 人格信息。

    仅更新请求体中提供的字段（非 None 值）。

    Args:
        persona_id: AI 人格 ID
        request: 更新请求
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        PersonaOut: 更新后的 AI 人格信息
    """
    result = await db.execute(select(AIPersona).where(AIPersona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    update_data = request.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(persona, field, value)

    await db.commit()
    await db.refresh(persona)

    return PersonaOut(
        id=persona.id,
        name=persona.name,
        bio=persona.bio,
        profession=persona.profession,
        gender_tag=persona.gender_tag,
        category=persona.category,
        archetype=persona.archetype,
        base_face_url=persona.base_face_url,
        visual_prompt_tags=persona.visual_prompt_tags,
        avatar_url=persona.avatar_url,
        is_active=persona.is_active,
    )


# ── 用户管理 ───────────────────────────────────────────────────

@router.get("/users", response_model=list[UserOut])
async def list_users(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    获取所有用户列表（管理视图）。

    按创建时间降序排列返回分页结果。

    Args:
        limit: 返回数量上限（默认 50）
        offset: 偏移量
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        list[UserOut]: 用户列表
    """
    result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
    )
    users = result.scalars().all()
    return [
        UserOut(
            id=u.id,
            email=u.email,
            nickname=u.nickname,
            avatar_url=u.avatar_url,
            gem_balance=u.gem_balance,
            is_admin=u.is_admin,
            created_at=_to_utc_iso(u.created_at),
        )
        for u in users
    ]


@router.post("/users/{user_id}/set-admin")
async def set_user_admin(
    user_id: int,
    is_admin: int = 1,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    设置或移除用户的管理员权限。

    Args:
        user_id: 用户 ID
        is_admin: 管理员状态（1=管理员，0=普通用户）
        db: 异步数据库会话
        admin: 当前管理员用户

    Returns:
        dict: 成功消息和更新后的状态

    Raises:
        HTTPException: 用户不存在时返回 404 错误
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_admin = is_admin
    await db.commit()
    return {"message": "Admin role updated", "user_id": user_id, "is_admin": is_admin}