"""
SoulPulse Admin: Outfit & Scene Configuration API (Plan Task 2)

\u63d0\u4f9b\u670d\u88c5/\u573a\u666f\u914d\u7f6e\u7684\u540e\u53f0\u7ba1\u7406\u63a5\u53e3\uff1a
- \u5217\u8868 / \u521b\u5efa / \u4fee\u6539 / \u8f6f\u5220\u9664
- \u8bbe\u7f6e\u67d0\u4e2a\u670d\u88c5\u4e3a\u8be5\u89d2\u8272\u7684\u9ed8\u8ba4\u9020\u578b
- \u67e5\u8be2\u67d0\u7528\u6237\u5728\u67d0\u89d2\u8272\u4e0b\u53ef\u7528\uff08\u5df2\u89e3\u9501\u6216\u514d\u8d39\uff09\u7684\u670d\u88c5\u5217\u8868
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import get_current_admin_user
from core.database import get_db
from models.outfit_config import OutfitConfig, UserOutfitUnlock

router = APIRouter(tags=["admin-outfits"])


# ── Schemas ──────────────────────────────────────────


class OutfitOut(BaseModel):
    id: int
    persona_id: int
    outfit_name: str
    category: str
    visual_prompt_override: str
    scene_prompt: Optional[str] = None
    unlock_condition_json: Optional[dict] = None
    thumbnail_url: Optional[str] = None
    is_default: bool
    is_active: bool
    sort_order: int


def _serialize(outfit: OutfitConfig) -> OutfitOut:
    return OutfitOut(
        id=outfit.id,
        persona_id=outfit.persona_id,
        outfit_name=outfit.outfit_name,
        category=outfit.category,
        visual_prompt_override=outfit.visual_prompt_override,
        scene_prompt=outfit.scene_prompt,
        unlock_condition_json=outfit.unlock_condition_json or {},
        thumbnail_url=outfit.thumbnail_url,
        is_default=bool(outfit.is_default),
        is_active=bool(outfit.is_active),
        sort_order=outfit.sort_order,
    )


# ── CRUD ──────────────────────────────────────────


@router.get("/outfits")
async def list_outfits(
    persona_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """\u5217\u51fa\u670d\u88c5\u914d\u7f6e\uff0c\u652f\u6301\u6309 persona / category / \u542f\u7528\u72b6\u6001\u8fc7\u6ee4\u3002"""
    stmt = select(OutfitConfig)
    if persona_id is not None:
        stmt = stmt.where(OutfitConfig.persona_id == persona_id)
    if category:
        stmt = stmt.where(OutfitConfig.category == category)
    if not include_inactive:
        stmt = stmt.where(OutfitConfig.is_active == True)
    stmt = stmt.order_by(OutfitConfig.persona_id, OutfitConfig.sort_order, OutfitConfig.id)

    result = await db.execute(stmt)
    return [_serialize(o) for o in result.scalars().all()]


@router.post("/outfits")
async def create_outfit(
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """\u521b\u5efa\u4e00\u4e2a\u65b0\u670d\u88c5\u914d\u7f6e\u3002

    \u5fc5\u586b\uff1a persona_id, outfit_name, category, visual_prompt_override
    \u53ef\u9009\uff1a scene_prompt, unlock_condition_json, thumbnail_url,
           is_default, is_active, sort_order
    """
    required = ("persona_id", "outfit_name", "category", "visual_prompt_override")
    missing = [k for k in required if k not in data or data.get(k) in (None, "")]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {missing}")

    outfit = OutfitConfig(
        persona_id=int(data["persona_id"]),
        outfit_name=str(data["outfit_name"]),
        category=str(data["category"]),
        visual_prompt_override=str(data["visual_prompt_override"]),
        scene_prompt=data.get("scene_prompt"),
        unlock_condition_json=data.get("unlock_condition_json") or {},
        thumbnail_url=data.get("thumbnail_url"),
        is_default=bool(data.get("is_default", False)),
        is_active=bool(data.get("is_active", True)),
        sort_order=int(data.get("sort_order", 0)),
    )
    db.add(outfit)

    # \u5982\u679c\u521b\u5efa\u65f6\u8bbe\u4e3a\u9ed8\u8ba4\uff0c\u9700\u53d6\u6d88\u540c persona \u4e0b\u5176\u4ed6\u9ed8\u8ba4
    if outfit.is_default:
        existing = await db.execute(
            select(OutfitConfig).where(
                OutfitConfig.persona_id == outfit.persona_id,
                OutfitConfig.is_default == True,
            )
        )
        for other in existing.scalars().all():
            other.is_default = False

    await db.commit()
    await db.refresh(outfit)
    return _serialize(outfit)


@router.put("/outfits/{outfit_id}")
async def update_outfit(
    outfit_id: int,
    data: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """\u66f4\u65b0\u670d\u88c5\u914d\u7f6e\u3002"""
    result = await db.execute(select(OutfitConfig).where(OutfitConfig.id == outfit_id))
    outfit = result.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")

    allowed = (
        "outfit_name",
        "category",
        "visual_prompt_override",
        "scene_prompt",
        "unlock_condition_json",
        "thumbnail_url",
        "is_default",
        "is_active",
        "sort_order",
    )
    for field in allowed:
        if field in data:
            setattr(outfit, field, data[field])

    if data.get("is_default"):
        # \u53d6\u6d88\u540c persona \u4e0b\u5176\u4ed6\u9ed8\u8ba4\u670d\u88c5
        existing = await db.execute(
            select(OutfitConfig).where(
                OutfitConfig.persona_id == outfit.persona_id,
                OutfitConfig.is_default == True,
                OutfitConfig.id != outfit.id,
            )
        )
        for other in existing.scalars().all():
            other.is_default = False

    await db.commit()
    await db.refresh(outfit)
    return _serialize(outfit)


@router.delete("/outfits/{outfit_id}")
async def delete_outfit(
    outfit_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """\u8f6f\u5220\u9664\u670d\u88c5\u3002\u8bbe\u7f6e is_active=False \u4ee5\u4fdd\u7559\u5386\u53f2\u8bb0\u5f55\u3002"""
    result = await db.execute(select(OutfitConfig).where(OutfitConfig.id == outfit_id))
    outfit = result.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")
    outfit.is_active = False
    await db.commit()
    return {"message": "Deleted", "id": outfit_id}


@router.post("/outfits/{outfit_id}/set-default")
async def set_default_outfit(
    outfit_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """\u5c06\u6307\u5b9a\u670d\u88c5\u8bbe\u4e3a\u8be5\u89d2\u8272\u7684\u9ed8\u8ba4\u670d\u88c5\u3002"""
    result = await db.execute(select(OutfitConfig).where(OutfitConfig.id == outfit_id))
    outfit = result.scalar_one_or_none()
    if not outfit:
        raise HTTPException(status_code=404, detail="Outfit not found")

    siblings = await db.execute(
        select(OutfitConfig).where(OutfitConfig.persona_id == outfit.persona_id)
    )
    for s in siblings.scalars().all():
        s.is_default = (s.id == outfit_id)

    await db.commit()
    await db.refresh(outfit)
    return _serialize(outfit)


@router.get("/outfits/{persona_id}/available")
async def get_available_outfits(
    persona_id: int,
    user_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """\u8fd4\u56de\u67d0\u7528\u6237\u5728\u67d0\u89d2\u8272\u4e0b\u53ef\u7528\uff08\u5df2\u89e3\u9501\u6216\u514d\u8d39\uff09\u7684\u670d\u88c5\u3002

    \u5224\u5b9a\u903b\u8f91:
    - unlock_condition_json.type = "free" \u2192 \u59cb\u7ec8\u53ef\u7528
    - \u5176\u4f59\u7c7b\u578b: \u9700 user_id \u4e14\u5728 user_outfit_unlocks \u4e2d\u5b58\u5728
    """
    stmt = (
        select(OutfitConfig)
        .where(
            OutfitConfig.persona_id == persona_id,
            OutfitConfig.is_active == True,
        )
        .order_by(OutfitConfig.sort_order, OutfitConfig.id)
    )
    result = await db.execute(stmt)
    outfits = result.scalars().all()

    unlocked_ids: set[int] = set()
    if user_id is not None:
        unlock_result = await db.execute(
            select(UserOutfitUnlock.outfit_id).where(
                UserOutfitUnlock.user_id == user_id
            )
        )
        unlocked_ids = {row[0] for row in unlock_result.all()}

    available = []
    for o in outfits:
        cond = o.unlock_condition_json or {}
        cond_type = cond.get("type", "free")
        is_available = (
            cond_type == "free"
            or o.is_default
            or o.id in unlocked_ids
        )
        item = _serialize(o).model_dump()
        item["available"] = is_available
        item["unlock_condition_type"] = cond_type
        available.append(item)
    return available
