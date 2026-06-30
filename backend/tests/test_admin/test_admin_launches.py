"""Admin character launch (campaigns / availability) endpoint tests."""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestAdminLaunches:
    """Tests for ``/api/admin/launches/*`` endpoints."""

    @pytest.mark.asyncio
    async def test_create_campaign(
        self, admin_client: AsyncClient, sample_persona
    ):
        """POST /campaigns creates a planned campaign with auto-derived phase boundaries."""
        launch_date = (datetime.utcnow() + timedelta(days=10)).isoformat()

        resp = await admin_client.post(
            "/api/admin/launches/campaigns",
            json={
                "persona_id": sample_persona.id,
                "campaign_name": "Spring Debut",
                "launch_date": launch_date,
                "launch_discount_percent": 25,
                "daily_post_boost": 4,
            },
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["persona_id"] == sample_persona.id
        assert data["campaign_name"] == "Spring Debut"
        assert data["current_phase"] == "planned"
        assert data["is_active"] is True
        assert data["launch_discount_percent"] == 25
        assert data["teaser_start"] is not None  # auto computed (launch - 3d)
        assert data["settling_end"] is not None  # auto computed (launch + 14d)

    @pytest.mark.asyncio
    async def test_advance_phase(
        self, admin_client: AsyncClient, sample_persona, db: AsyncSession
    ):
        """POST /campaigns/{id}/advance moves a campaign to the next phase."""
        from models.character_launch import CharacterLaunchCampaign

        launch_date = datetime.utcnow() + timedelta(days=10)
        campaign = CharacterLaunchCampaign(
            persona_id=sample_persona.id,
            campaign_name="Phase Advance Test",
            teaser_start=launch_date - timedelta(days=3),
            launch_date=launch_date,
            settling_end=launch_date + timedelta(days=14),
            current_phase="planned",
            is_active=True,
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)

        resp = await admin_client.post(
            f"/api/admin/launches/campaigns/{campaign.id}/advance"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["current_phase"] != "planned"

    @pytest.mark.asyncio
    async def test_get_availability(
        self, admin_client: AsyncClient, sample_persona, db: AsyncSession
    ):
        """GET /availability lists availability rules for personas."""
        from models.character_launch import CharacterAvailability

        rule = CharacterAvailability(
            persona_id=sample_persona.id,
            availability_type="permanent",
            rotation_priority=10,
        )
        db.add(rule)
        await db.commit()
        await db.refresh(rule)

        resp = await admin_client.get("/api/admin/launches/availability")
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert {"availability", "total"}.issubset(body.keys())
        persona_ids = [a["persona_id"] for a in body["availability"]]
        assert sample_persona.id in persona_ids
