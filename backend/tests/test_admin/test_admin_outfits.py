"""Admin outfits endpoint tests."""

import pytest
from httpx import AsyncClient


class TestAdminOutfits:
    """Tests for ``/api/admin/outfits*`` endpoints."""

    @pytest.mark.asyncio
    async def test_list_outfits(self, admin_client: AsyncClient, sample_outfit):
        """GET /outfits returns the seeded outfit when filtered by persona."""
        resp = await admin_client.get(
            "/api/admin/outfits", params={"persona_id": sample_outfit.persona_id}
        )
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert isinstance(body, list)
        names = [o["outfit_name"] for o in body]
        assert sample_outfit.outfit_name in names

    @pytest.mark.asyncio
    async def test_create_outfit(self, admin_client: AsyncClient, sample_persona):
        """POST /outfits accepts a free-form dict body and persists the outfit."""
        payload = {
            "persona_id": sample_persona.id,
            "outfit_name": "舞台装",
            "category": "event",
            "visual_prompt_override": "stage outfit, glittering jacket",
            "unlock_condition_json": {"type": "gem", "cost": 30},
            "is_default": False,
            "is_active": True,
            "sort_order": 3,
        }
        resp = await admin_client.post("/api/admin/outfits", json=payload)
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["outfit_name"] == "舞台装"
        assert data["category"] == "event"
        assert data["visual_prompt_override"] == "stage outfit, glittering jacket"
        assert data["is_default"] is False

    @pytest.mark.asyncio
    async def test_update_outfit(self, admin_client: AsyncClient, sample_outfit):
        """PUT /outfits/{id} updates editable fields."""
        resp = await admin_client.put(
            f"/api/admin/outfits/{sample_outfit.id}",
            json={"outfit_name": "改良衬衫", "sort_order": 10},
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["outfit_name"] == "改良衬衫"
        assert data["sort_order"] == 10
