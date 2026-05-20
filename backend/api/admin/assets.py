"""Admin API endpoints for asset registry management.

Provides endpoints for:
- Listing/filtering assets with pagination
- Review queue management (approve/reject workflow)
- Bulk operations
- Version history and rollback
- Consistency reporting
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user
from models.asset_registry import AssetRegistry
from services.asset_registry_service import asset_registry_service

router = APIRouter(tags=["admin-assets"])


# ── Pydantic Response Models ──────────────────────────────────────────


class AssetOut(BaseModel):
    id: int
    asset_type: str
    persona_id: int | None
    version: int
    url: str
    thumbnail_url: str | None
    metadata_json: dict | None
    status: str
    consistency_score: float | None
    review_notes: str | None
    created_by: str | None
    created_at: str
    updated_at: str


class BulkApproveRequest(BaseModel):
    asset_ids: list[int]


class RejectRequest(BaseModel):
    reason: str


def _asset_to_out(asset: AssetRegistry) -> AssetOut:
    """Convert ORM object to response model."""
    return AssetOut(
        id=asset.id,
        asset_type=asset.asset_type,
        persona_id=asset.persona_id,
        version=asset.version,
        url=asset.url,
        thumbnail_url=asset.thumbnail_url,
        metadata_json=asset.metadata_json,
        status=asset.status,
        consistency_score=asset.consistency_score,
        review_notes=asset.review_notes,
        created_by=asset.created_by,
        created_at=asset.created_at.isoformat() if asset.created_at else "",
        updated_at=asset.updated_at.isoformat() if asset.updated_at else "",
    )


# ── Endpoints ──────────────────────────────────────────


@router.get("/assets")
async def list_assets(
    status: str = Query(None, description="Filter by status: draft, review, active, archived"),
    persona_id: int = Query(None, description="Filter by persona ID"),
    asset_type: str = Query(None, description="Filter by asset type"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """List assets with filtering and pagination."""
    query = select(AssetRegistry).order_by(AssetRegistry.updated_at.desc())
    count_q = select(func.count()).select_from(AssetRegistry)

    if status:
        query = query.where(AssetRegistry.status == status)
        count_q = count_q.where(AssetRegistry.status == status)
    if persona_id:
        query = query.where(AssetRegistry.persona_id == persona_id)
        count_q = count_q.where(AssetRegistry.persona_id == persona_id)
    if asset_type:
        query = query.where(AssetRegistry.asset_type == asset_type)
        count_q = count_q.where(AssetRegistry.asset_type == asset_type)

    total = (await db.execute(count_q)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    assets = result.scalars().all()

    return {
        "assets": [_asset_to_out(a) for a in assets],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
    }


@router.get("/assets/review-queue")
async def get_review_queue(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Get all assets pending review."""
    assets = await asset_registry_service.get_assets_by_status(db, "review")
    return {
        "queue": [_asset_to_out(a) for a in assets],
        "count": len(assets),
    }


@router.post("/assets/{asset_id}/approve")
async def approve_asset(
    asset_id: int,
    notes: str = Query(None, description="Optional approval notes"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Approve an asset (review -> active)."""
    try:
        asset = await asset_registry_service.update_status(
            db, asset_id, "active", review_notes=notes
        )
        return _asset_to_out(asset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/assets/{asset_id}/reject")
async def reject_asset(
    asset_id: int,
    body: RejectRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Reject an asset with reason (review -> draft)."""
    try:
        asset = await asset_registry_service.update_status(
            db, asset_id, "draft", review_notes=f"Rejected: {body.reason}"
        )
        return _asset_to_out(asset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/assets/bulk-approve")
async def bulk_approve(
    body: BulkApproveRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Batch approve multiple assets."""
    updated = await asset_registry_service.bulk_update_status(
        db, body.asset_ids, "active"
    )
    return {
        "approved": [_asset_to_out(a) for a in updated],
        "count": len(updated),
        "requested": len(body.asset_ids),
    }


@router.get("/assets/{persona_id}/history")
async def get_version_history(
    persona_id: int,
    asset_type: str = Query(None, description="Filter by asset type"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Get version history for a persona's assets."""
    if asset_type:
        history = await asset_registry_service.get_version_history(
            db, persona_id, asset_type
        )
    else:
        # Get all asset types for this persona
        result = await db.execute(
            select(AssetRegistry)
            .where(AssetRegistry.persona_id == persona_id)
            .order_by(AssetRegistry.asset_type, AssetRegistry.version.desc())
        )
        history = list(result.scalars().all())

    return {
        "persona_id": persona_id,
        "history": [_asset_to_out(a) for a in history],
        "count": len(history),
    }


@router.post("/assets/{asset_id}/rollback")
async def rollback_asset(
    asset_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Rollback to a previous asset version."""
    try:
        asset = await asset_registry_service.rollback_to_version(db, asset_id)
        return _asset_to_out(asset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/assets/consistency-report")
async def consistency_report(
    persona_id: int = Query(None, description="Filter by persona ID"),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Get visual consistency report."""
    report = await asset_registry_service.get_consistency_report(db, persona_id)
    return report
