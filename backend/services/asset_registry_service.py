"""
Asset Registry Service - 视觉资产生命周期管理服务

Manages visual asset registration, versioning, review workflow, and consistency tracking.

Responsibilities:
- Register new assets with auto-versioning
- Status workflow: draft -> review -> active -> archived
- Version history and rollback
- Bulk operations for admin review queues
- Consistency reporting across personas
"""

from datetime import datetime, timezone

from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.asset_registry import AssetRegistry


# Valid status transitions
_VALID_TRANSITIONS = {
    "draft": ["review", "archived"],
    "review": ["active", "draft", "archived"],
    "active": ["archived"],
    "archived": ["active"],  # re-activation via rollback
}

# Valid asset types
VALID_ASSET_TYPES = [
    "avatar", "post", "story", "outfit", "cg", "background", "expression"
]


class AssetRegistryService:
    """Manages visual asset registration, versioning, review workflow, and consistency tracking."""

    async def register_asset(
        self,
        db: AsyncSession,
        asset_type: str,
        persona_id: int,
        url: str,
        metadata: dict = None,
        created_by: str = None,
    ) -> AssetRegistry:
        """
        Register a new asset in the system.

        Auto-increments the version number for the same persona + asset_type combination.
        """
        if asset_type not in VALID_ASSET_TYPES:
            raise ValueError(f"Invalid asset_type: {asset_type}. Must be one of {VALID_ASSET_TYPES}")

        # Determine next version number
        result = await db.execute(
            select(func.max(AssetRegistry.version))
            .where(AssetRegistry.persona_id == persona_id)
            .where(AssetRegistry.asset_type == asset_type)
        )
        max_version = result.scalar() or 0
        next_version = max_version + 1

        asset = AssetRegistry(
            asset_type=asset_type,
            persona_id=persona_id,
            version=next_version,
            url=url,
            metadata_json=metadata,
            status="draft",
            created_by=created_by,
        )
        db.add(asset)
        await db.commit()
        await db.refresh(asset)
        return asset

    async def update_status(
        self,
        db: AsyncSession,
        asset_id: int,
        new_status: str,
        review_notes: str = None,
    ) -> AssetRegistry:
        """
        Update asset status with validation of allowed transitions.

        Allowed transitions:
        - draft -> review, archived
        - review -> active, draft, archived
        - active -> archived
        - archived -> active (rollback)
        """
        result = await db.execute(
            select(AssetRegistry).where(AssetRegistry.id == asset_id)
        )
        asset = result.scalar_one_or_none()
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")

        allowed = _VALID_TRANSITIONS.get(asset.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{asset.status}' to '{new_status}'. "
                f"Allowed: {allowed}"
            )

        asset.status = new_status
        if review_notes is not None:
            asset.review_notes = review_notes

        # When activating, archive other active versions of same type+persona
        if new_status == "active" and asset.persona_id:
            await db.execute(
                update(AssetRegistry)
                .where(AssetRegistry.persona_id == asset.persona_id)
                .where(AssetRegistry.asset_type == asset.asset_type)
                .where(AssetRegistry.status == "active")
                .where(AssetRegistry.id != asset_id)
                .values(status="archived")
            )

        await db.commit()
        await db.refresh(asset)
        return asset

    async def get_assets_by_status(
        self,
        db: AsyncSession,
        status: str,
        persona_id: int = None,
        asset_type: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list:
        """Get assets filtered by status, optionally by persona and type."""
        query = (
            select(AssetRegistry)
            .where(AssetRegistry.status == status)
            .order_by(AssetRegistry.updated_at.desc())
        )

        if persona_id is not None:
            query = query.where(AssetRegistry.persona_id == persona_id)
        if asset_type is not None:
            query = query.where(AssetRegistry.asset_type == asset_type)

        query = query.offset(offset).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_version_history(
        self,
        db: AsyncSession,
        persona_id: int,
        asset_type: str,
    ) -> list:
        """Get version history for a specific asset type of a persona, ordered by version desc."""
        result = await db.execute(
            select(AssetRegistry)
            .where(AssetRegistry.persona_id == persona_id)
            .where(AssetRegistry.asset_type == asset_type)
            .order_by(AssetRegistry.version.desc())
        )
        return list(result.scalars().all())

    async def rollback_to_version(
        self,
        db: AsyncSession,
        asset_id: int,
    ) -> AssetRegistry:
        """
        Rollback: archive current active asset and reactivate the specified version.

        Steps:
        1. Find the target asset
        2. Archive all currently active assets of same persona+type
        3. Set target asset to active
        """
        result = await db.execute(
            select(AssetRegistry).where(AssetRegistry.id == asset_id)
        )
        target = result.scalar_one_or_none()
        if not target:
            raise ValueError(f"Asset {asset_id} not found")

        if not target.persona_id:
            raise ValueError("Cannot rollback asset without persona_id")

        # Archive all currently active versions of same persona+type
        await db.execute(
            update(AssetRegistry)
            .where(AssetRegistry.persona_id == target.persona_id)
            .where(AssetRegistry.asset_type == target.asset_type)
            .where(AssetRegistry.status == "active")
            .values(status="archived")
        )

        # Reactivate target
        target.status = "active"
        target.review_notes = f"Rolled back to version {target.version} at {datetime.now(timezone.utc).isoformat()}"

        await db.commit()
        await db.refresh(target)
        return target

    async def bulk_update_status(
        self,
        db: AsyncSession,
        asset_ids: list[int],
        new_status: str,
    ) -> list:
        """
        Batch status update for multiple assets.

        Validates each transition individually and returns updated assets.
        Skips assets with invalid transitions (logs warning).
        """
        updated = []
        for asset_id in asset_ids:
            try:
                asset = await self.update_status(db, asset_id, new_status)
                updated.append(asset)
            except ValueError:
                # Skip invalid transitions in bulk operations
                continue
        return updated

    async def get_consistency_report(
        self,
        db: AsyncSession,
        persona_id: int = None,
    ) -> dict:
        """
        Generate consistency report with scores and flagged assets.

        Returns:
            {
                "total_assets": int,
                "scored_assets": int,
                "average_score": float,
                "below_threshold": [asset_ids],
                "by_persona": {persona_id: {"avg_score": float, "count": int}},
            }
        """
        query = select(AssetRegistry).where(AssetRegistry.status == "active")
        if persona_id is not None:
            query = query.where(AssetRegistry.persona_id == persona_id)

        result = await db.execute(query)
        assets = list(result.scalars().all())

        scored = [a for a in assets if a.consistency_score is not None]
        below_threshold = [a.id for a in scored if a.consistency_score < 0.8]

        # Group by persona
        by_persona: dict = {}
        for asset in scored:
            pid = asset.persona_id
            if pid not in by_persona:
                by_persona[pid] = {"scores": [], "count": 0}
            by_persona[pid]["scores"].append(asset.consistency_score)
            by_persona[pid]["count"] += 1

        # Calculate averages
        persona_summary = {}
        for pid, data in by_persona.items():
            avg = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            persona_summary[pid] = {
                "avg_score": round(avg, 3),
                "count": data["count"],
            }

        overall_avg = (
            sum(a.consistency_score for a in scored) / len(scored)
            if scored
            else 0
        )

        return {
            "total_assets": len(assets),
            "scored_assets": len(scored),
            "average_score": round(overall_avg, 3),
            "below_threshold": below_threshold,
            "by_persona": persona_summary,
        }


# Singleton instance
asset_registry_service = AssetRegistryService()
