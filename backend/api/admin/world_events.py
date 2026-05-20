"""Admin endpoints for world event management.

Provides CRUD over WorldEvent. Mounted under ``/api/admin/world-events`` from
``api/admin/__init__.py``.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import get_current_admin_user
from core.database import get_db
from models.world_event import WorldEvent

router = APIRouter(prefix="/world-events", tags=["admin-world-events"])


# ── Pydantic schemas ───────────────────────────────────────────


class WorldEventOut(BaseModel):
    id: int
    event_type: str
    title: str
    description: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    affected_persona_ids: list
    mood_modifier_json: dict
    content_directive: Optional[str]
    is_active: bool
    created_at: Optional[str]


class WorldEventCreate(BaseModel):
    event_type: str = Field(..., max_length=50)
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    affected_persona_ids: list[int] = Field(default_factory=list)
    mood_modifier_json: dict = Field(default_factory=dict)
    content_directive: Optional[str] = None
    is_active: bool = True


class WorldEventUpdate(BaseModel):
    event_type: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    affected_persona_ids: Optional[list[int]] = None
    mood_modifier_json: Optional[dict] = None
    content_directive: Optional[str] = None
    is_active: Optional[bool] = None


def _event_to_out(e: WorldEvent) -> WorldEventOut:
    return WorldEventOut(
        id=e.id,
        event_type=e.event_type,
        title=e.title,
        description=e.description,
        start_date=e.start_date.isoformat() if e.start_date else None,
        end_date=e.end_date.isoformat() if e.end_date else None,
        affected_persona_ids=e.affected_persona_ids or [],
        mood_modifier_json=e.mood_modifier_json or {},
        content_directive=e.content_directive,
        is_active=bool(e.is_active),
        created_at=e.created_at.isoformat() if e.created_at else None,
    )


# ── Endpoints ──────────────────────────────────────────────────


@router.get("/")
async def list_world_events(
    is_active: Optional[bool] = Query(None),
    event_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """List world events with optional filtering."""
    query = select(WorldEvent).order_by(WorldEvent.start_date.desc())
    if is_active is not None:
        query = query.where(WorldEvent.is_active.is_(is_active))
    if event_type:
        query = query.where(WorldEvent.event_type == event_type)
    rows = (await db.execute(query)).scalars().all()
    return {
        "events": [_event_to_out(e) for e in rows],
        "total": len(rows),
    }


@router.post("/")
async def create_world_event(
    body: WorldEventCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Create a new world event."""
    event = WorldEvent(**body.model_dump())
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return _event_to_out(event)


@router.put("/{event_id}")
async def update_world_event(
    event_id: int,
    body: WorldEventUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Update a world event."""
    result = await db.execute(select(WorldEvent).where(WorldEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="World event not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(event, field, value)
    await db.commit()
    await db.refresh(event)
    return _event_to_out(event)


@router.delete("/{event_id}")
async def deactivate_world_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Deactivate a world event (soft delete)."""
    result = await db.execute(select(WorldEvent).where(WorldEvent.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="World event not found")
    event.is_active = False
    await db.commit()
    return {"message": "World event deactivated", "id": event_id}
