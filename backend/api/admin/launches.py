"""Admin endpoints for character launch campaign management (Plan Task 9.3-9.4).

Mounted under ``/api/admin/launches`` from ``api/admin/__init__.py``.

Endpoints:
- ``GET    /campaigns``                    list campaigns (filter by status)
- ``POST   /campaigns``                    create a new campaign
- ``GET    /campaigns/{id}``               campaign detail + phase progress
- ``PUT    /campaigns/{id}``               update campaign config (pre-teaser only)
- ``DELETE /campaigns/{id}``               cancel an active campaign
- ``POST   /campaigns/{id}/advance``       force-advance to the next phase
- ``GET    /availability``                 list availability rules
- ``PUT    /availability/{persona_id}``    upsert availability rule
- ``POST   /process``                      run process_campaigns immediately
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.admin.dependencies import get_current_admin_user
from core.database import get_db
from models.ai_persona import AIPersona
from models.character_launch import CharacterAvailability, CharacterLaunchCampaign
from services.character_launch_service import (
    PHASE_INTEGRATED,
    PHASE_PLANNED,
    PHASE_TEASER,
    character_launch_service,
)

router = APIRouter(prefix="/launches", tags=["admin-launches"])


# ── Pydantic schemas ───────────────────────────────────────────


class CampaignOut(BaseModel):
    id: int
    persona_id: int
    campaign_name: str
    teaser_start: Optional[str]
    launch_date: Optional[str]
    settling_end: Optional[str]
    teaser_silhouette_url: Optional[str]
    teaser_hints_json: Optional[list]
    reveal_cg_url: Optional[str]
    welcome_scene_id: Optional[int]
    launch_gacha_id: Optional[int]
    launch_discount_percent: int
    daily_post_boost: int
    launch_event_json: Optional[dict]
    current_phase: str
    is_active: bool
    created_at: Optional[str]


class CampaignCreate(BaseModel):
    persona_id: int
    campaign_name: str = Field(..., max_length=200)
    launch_date: datetime
    teaser_silhouette_url: Optional[str] = None
    teaser_hints_json: Optional[list] = None
    reveal_cg_url: Optional[str] = None
    welcome_scene_id: Optional[int] = None
    launch_gacha_id: Optional[int] = None
    launch_discount_percent: int = 20
    daily_post_boost: int = 3
    launch_event_json: Optional[dict] = None


class CampaignUpdate(BaseModel):
    campaign_name: Optional[str] = None
    launch_date: Optional[datetime] = None
    teaser_silhouette_url: Optional[str] = None
    teaser_hints_json: Optional[list] = None
    reveal_cg_url: Optional[str] = None
    welcome_scene_id: Optional[int] = None
    launch_gacha_id: Optional[int] = None
    launch_discount_percent: Optional[int] = None
    daily_post_boost: Optional[int] = None
    launch_event_json: Optional[dict] = None


class AvailabilityUpsert(BaseModel):
    availability_type: str = Field(..., pattern="^(permanent|seasonal|limited|archived)$")
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None
    archive_pass_required: bool = False
    rotation_priority: int = 0


class AvailabilityOut(BaseModel):
    id: int
    persona_id: int
    availability_type: str
    available_from: Optional[str]
    available_until: Optional[str]
    archive_pass_required: bool
    rotation_priority: int


def _campaign_to_out(c: CharacterLaunchCampaign) -> CampaignOut:
    return CampaignOut(
        id=c.id,
        persona_id=c.persona_id,
        campaign_name=c.campaign_name,
        teaser_start=c.teaser_start.isoformat() if c.teaser_start else None,
        launch_date=c.launch_date.isoformat() if c.launch_date else None,
        settling_end=c.settling_end.isoformat() if c.settling_end else None,
        teaser_silhouette_url=c.teaser_silhouette_url,
        teaser_hints_json=c.teaser_hints_json or [],
        reveal_cg_url=c.reveal_cg_url,
        welcome_scene_id=c.welcome_scene_id,
        launch_gacha_id=c.launch_gacha_id,
        launch_discount_percent=c.launch_discount_percent,
        daily_post_boost=c.daily_post_boost,
        launch_event_json=c.launch_event_json or {},
        current_phase=c.current_phase,
        is_active=bool(c.is_active),
        created_at=c.created_at.isoformat() if c.created_at else None,
    )


def _availability_to_out(a: CharacterAvailability) -> AvailabilityOut:
    return AvailabilityOut(
        id=a.id,
        persona_id=a.persona_id,
        availability_type=a.availability_type,
        available_from=a.available_from.isoformat() if a.available_from else None,
        available_until=a.available_until.isoformat() if a.available_until else None,
        archive_pass_required=bool(a.archive_pass_required),
        rotation_priority=a.rotation_priority,
    )


# ── Campaign endpoints ─────────────────────────────────────────


@router.get("/campaigns")
async def list_campaigns(
    status: Optional[str] = Query(
        None,
        description="Filter by current_phase: planned/teaser/launched/settling/integrated",
    ),
    persona_id: Optional[int] = Query(None),
    is_active: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """List launch campaigns with optional filtering."""
    query = select(CharacterLaunchCampaign).order_by(
        CharacterLaunchCampaign.launch_date.desc()
    )
    if status:
        query = query.where(CharacterLaunchCampaign.current_phase == status)
    if persona_id is not None:
        query = query.where(CharacterLaunchCampaign.persona_id == persona_id)
    if is_active is not None:
        query = query.where(CharacterLaunchCampaign.is_active.is_(is_active))

    rows = (await db.execute(query)).scalars().all()
    return {
        "campaigns": [_campaign_to_out(c) for c in rows],
        "total": len(rows),
    }


@router.post("/campaigns")
async def create_campaign(
    body: CampaignCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Create a new launch campaign.

    Validates that the persona exists, the launch date is in the
    future, and that no other active campaign already exists for the
    same persona.
    """
    if body.launch_date <= datetime.utcnow():
        raise HTTPException(status_code=400, detail="launch_date must be in the future")

    persona = await db.get(AIPersona, body.persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="persona not found")

    existing = await db.execute(
        select(CharacterLaunchCampaign).where(
            CharacterLaunchCampaign.persona_id == body.persona_id,
            CharacterLaunchCampaign.is_active.is_(True),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="an active campaign already exists for this persona",
        )

    config = body.model_dump(exclude={"persona_id", "campaign_name", "launch_date"})
    try:
        campaign = await character_launch_service.create_campaign(
            db,
            persona_id=body.persona_id,
            launch_date=body.launch_date,
            campaign_name=body.campaign_name,
            config=config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _campaign_to_out(campaign)


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Return a single campaign with phase progress metadata."""
    campaign = await db.get(CharacterLaunchCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")

    now = datetime.utcnow()
    progress: dict[str, Any] = {
        "current_phase": campaign.current_phase,
        "now": now.isoformat(),
    }
    if campaign.teaser_start:
        progress["seconds_until_teaser"] = int(
            (campaign.teaser_start - now).total_seconds()
        )
    if campaign.launch_date:
        progress["seconds_until_launch"] = int(
            (campaign.launch_date - now).total_seconds()
        )
    if campaign.settling_end:
        progress["seconds_until_integrated"] = int(
            (campaign.settling_end - now).total_seconds()
        )

    return {
        "campaign": _campaign_to_out(campaign),
        "progress": progress,
    }


@router.put("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: int,
    body: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Update a campaign. Only allowed while in the ``planned`` phase."""
    campaign = await db.get(CharacterLaunchCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    if campaign.current_phase != PHASE_PLANNED:
        raise HTTPException(
            status_code=400,
            detail=(
                "campaign already past planned phase; "
                f"current_phase={campaign.current_phase}"
            ),
        )

    payload = body.model_dump(exclude_none=True)

    # If the launch date is being moved, recompute teaser_start/settling_end.
    if "launch_date" in payload:
        new_launch: datetime = payload["launch_date"]
        if new_launch <= datetime.utcnow():
            raise HTTPException(status_code=400, detail="launch_date must be in the future")
        from datetime import timedelta
        campaign.teaser_start = new_launch - timedelta(days=3)
        campaign.settling_end = new_launch + timedelta(days=14)

    for field, value in payload.items():
        setattr(campaign, field, value)

    await db.commit()
    await db.refresh(campaign)
    return _campaign_to_out(campaign)


@router.post("/campaigns/{campaign_id}/advance")
async def advance_phase(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Manually advance a campaign to the next phase."""
    campaign = await db.get(CharacterLaunchCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")

    try:
        campaign = await character_launch_service.advance_phase(db, campaign)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _campaign_to_out(campaign)


@router.delete("/campaigns/{campaign_id}")
async def cancel_campaign(
    campaign_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Cancel an active campaign (sets ``is_active=False``)."""
    campaign = await db.get(CharacterLaunchCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="campaign not found")
    if campaign.current_phase == PHASE_INTEGRATED:
        raise HTTPException(status_code=400, detail="campaign already integrated")

    campaign.is_active = False
    await db.commit()
    return {"message": "campaign cancelled", "id": campaign_id}


# ── Availability endpoints ─────────────────────────────────────


@router.get("/availability")
async def list_availability(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """List all character availability rules."""
    result = await db.execute(
        select(CharacterAvailability).order_by(
            CharacterAvailability.rotation_priority.desc(),
            CharacterAvailability.persona_id,
        )
    )
    rows = result.scalars().all()
    return {
        "availability": [_availability_to_out(a) for a in rows],
        "total": len(rows),
    }


@router.put("/availability/{persona_id}")
async def set_availability(
    persona_id: int,
    body: AvailabilityUpsert,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Create or update the availability rule for ``persona_id``."""
    persona = await db.get(AIPersona, persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail="persona not found")

    if body.availability_type in ("seasonal", "limited"):
        if not (body.available_from and body.available_until):
            raise HTTPException(
                status_code=400,
                detail="seasonal/limited availability requires available_from and available_until",
            )
        if body.available_from >= body.available_until:
            raise HTTPException(
                status_code=400,
                detail="available_from must be before available_until",
            )

    try:
        avail = await character_launch_service.set_availability(
            db,
            persona_id=persona_id,
            availability_type=body.availability_type,
            available_from=body.available_from,
            available_until=body.available_until,
            archive_pass_required=body.archive_pass_required,
            rotation_priority=body.rotation_priority,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _availability_to_out(avail)


# ── Manual processing trigger ──────────────────────────────────


@router.post("/process")
async def trigger_processing(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Manually run :func:`process_campaigns` (testing / admin override)."""
    counters = await character_launch_service.process_campaigns(db)
    return {"status": "processed", "transitions": counters}
