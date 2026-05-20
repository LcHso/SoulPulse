"""Admin endpoints for scene management.

Provides CRUD over ChatScene plus completion statistics. Mounted under
``/api/admin/scenes`` from ``api/admin/__init__.py``.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import get_current_admin_user
from core.database import get_db
from models.chat_scene import ChatScene, UserSceneProgress

router = APIRouter(prefix="/scenes", tags=["admin-scenes"])


# ── Pydantic schemas ───────────────────────────────────────────


class SceneOut(BaseModel):
    id: int
    persona_id: int
    scene_name: str
    scene_type: str
    setting_description: str
    mood_preset: Optional[str]
    system_prompt_addon: str
    required_intimacy: int
    unlock_type: str
    unlock_cost: int
    max_messages: int
    completion_reward_json: Optional[dict]
    scene_cg_url: Optional[str]
    is_active: bool
    sort_order: int
    created_at: Optional[str]


class SceneCreate(BaseModel):
    persona_id: int
    scene_name: str = Field(..., max_length=200)
    scene_type: str = Field(..., max_length=50)
    setting_description: str
    system_prompt_addon: str
    mood_preset: Optional[str] = None
    required_intimacy: int = 0
    unlock_type: str = "free"
    unlock_cost: int = 0
    max_messages: int = 20
    completion_reward_json: Optional[dict] = None
    scene_cg_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class SceneUpdate(BaseModel):
    scene_name: Optional[str] = None
    scene_type: Optional[str] = None
    setting_description: Optional[str] = None
    system_prompt_addon: Optional[str] = None
    mood_preset: Optional[str] = None
    required_intimacy: Optional[int] = None
    unlock_type: Optional[str] = None
    unlock_cost: Optional[int] = None
    max_messages: Optional[int] = None
    completion_reward_json: Optional[dict] = None
    scene_cg_url: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


def _scene_to_out(s: ChatScene) -> SceneOut:
    return SceneOut(
        id=s.id,
        persona_id=s.persona_id,
        scene_name=s.scene_name,
        scene_type=s.scene_type,
        setting_description=s.setting_description,
        mood_preset=s.mood_preset,
        system_prompt_addon=s.system_prompt_addon,
        required_intimacy=s.required_intimacy,
        unlock_type=s.unlock_type,
        unlock_cost=s.unlock_cost,
        max_messages=s.max_messages,
        completion_reward_json=s.completion_reward_json,
        scene_cg_url=s.scene_cg_url,
        is_active=bool(s.is_active),
        sort_order=s.sort_order,
        created_at=s.created_at.isoformat() if s.created_at else None,
    )


# ── Endpoints ──────────────────────────────────────────────────


@router.get("/")
async def list_scenes(
    persona_id: Optional[int] = Query(None, description="Filter by persona ID"),
    scene_type: Optional[str] = Query(None, description="Filter by scene type"),
    unlock_type: Optional[str] = Query(None, description="Filter by unlock type"),
    is_active: Optional[bool] = Query(None, description="Filter by active flag"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """List scenes with optional filtering and pagination."""
    query = select(ChatScene).order_by(
        ChatScene.persona_id, ChatScene.sort_order, ChatScene.id
    )
    count_q = select(func.count()).select_from(ChatScene)

    if persona_id is not None:
        query = query.where(ChatScene.persona_id == persona_id)
        count_q = count_q.where(ChatScene.persona_id == persona_id)
    if scene_type:
        query = query.where(ChatScene.scene_type == scene_type)
        count_q = count_q.where(ChatScene.scene_type == scene_type)
    if unlock_type:
        query = query.where(ChatScene.unlock_type == unlock_type)
        count_q = count_q.where(ChatScene.unlock_type == unlock_type)
    if is_active is not None:
        query = query.where(ChatScene.is_active.is_(is_active))
        count_q = count_q.where(ChatScene.is_active.is_(is_active))

    total = (await db.execute(count_q)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    scenes = result.scalars().all()

    return {
        "scenes": [_scene_to_out(s) for s in scenes],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
    }


@router.post("/")
async def create_scene(
    body: SceneCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Create a new scene."""
    scene = ChatScene(**body.model_dump())
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    return _scene_to_out(scene)


@router.put("/{scene_id}")
async def update_scene(
    scene_id: int,
    body: SceneUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Update an existing scene."""
    result = await db.execute(select(ChatScene).where(ChatScene.id == scene_id))
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(scene, field, value)

    await db.commit()
    await db.refresh(scene)
    return _scene_to_out(scene)


@router.delete("/{scene_id}")
async def delete_scene(
    scene_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Soft-delete a scene (sets is_active=False)."""
    result = await db.execute(select(ChatScene).where(ChatScene.id == scene_id))
    scene = result.scalar_one_or_none()
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    scene.is_active = False
    await db.commit()
    return {"message": "Scene archived", "id": scene_id}


@router.get("/stats")
async def scene_stats(
    persona_id: Optional[int] = Query(None, description="Filter by persona ID"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Aggregate completion statistics across scenes.

    Returns per-scene counts of in_progress / completed / abandoned sessions
    plus average ``messages_count`` for completed sessions.
    """
    progress_q = select(
        UserSceneProgress.scene_id,
        UserSceneProgress.status,
        func.count(UserSceneProgress.id),
        func.avg(UserSceneProgress.messages_count),
    ).group_by(UserSceneProgress.scene_id, UserSceneProgress.status)

    if persona_id is not None:
        progress_q = progress_q.where(UserSceneProgress.persona_id == persona_id)

    rows = (await db.execute(progress_q)).all()

    by_scene: dict[int, dict] = {}
    for scene_id, status, count, avg_msgs in rows:
        bucket = by_scene.setdefault(
            scene_id,
            {
                "scene_id": scene_id,
                "in_progress": 0,
                "completed": 0,
                "abandoned": 0,
                "avg_completed_messages": 0.0,
            },
        )
        if status in ("in_progress", "completed", "abandoned"):
            bucket[status] = int(count or 0)
        if status == "completed":
            bucket["avg_completed_messages"] = float(avg_msgs or 0.0)

    # Attach scene names for readability.
    if by_scene:
        scene_q = select(ChatScene).where(ChatScene.id.in_(list(by_scene.keys())))
        for scene in (await db.execute(scene_q)).scalars().all():
            by_scene[scene.id]["scene_name"] = scene.scene_name
            by_scene[scene.id]["persona_id"] = scene.persona_id

    return {
        "stats": list(by_scene.values()),
        "count": len(by_scene),
    }
