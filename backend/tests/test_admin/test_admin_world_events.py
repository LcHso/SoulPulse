"""Admin world-event endpoint tests."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


class TestAdminWorldEvents:
    """Tests for ``/api/admin/world-events/*`` endpoints."""

    @pytest.mark.asyncio
    async def test_create_world_event(self, admin_client: AsyncClient, sample_persona):
        """POST /world-events/ creates a new event."""
        payload = {
            "event_type": "holiday",
            "title": "中秋",
            "description": "中秋节假期",
            "start_date": datetime(2026, 9, 25, tzinfo=timezone.utc).isoformat(),
            "end_date": datetime(2026, 9, 28, tzinfo=timezone.utc).isoformat(),
            "affected_persona_ids": [sample_persona.id],
            "mood_modifier_json": {"pleasure": 0.3},
            "is_active": True,
        }
        resp = await admin_client.post("/api/admin/world-events/", json=payload)
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["title"] == "中秋"
        assert data["event_type"] == "holiday"
        assert sample_persona.id in data["affected_persona_ids"]
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_update_world_event(
        self, admin_client: AsyncClient, sample_world_event
    ):
        """PUT /world-events/{id} mutates editable fields."""
        resp = await admin_client.put(
            f"/api/admin/world-events/{sample_world_event.id}",
            json={"title": "春节 (updated)", "is_active": False},
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["title"] == "春节 (updated)"
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_list_world_events(
        self, admin_client: AsyncClient, sample_world_event
    ):
        """GET /world-events/ returns events with the envelope contract."""
        resp = await admin_client.get(
            "/api/admin/world-events/", params={"is_active": True}
        )
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert {"events", "total"}.issubset(body.keys())
        assert body["total"] >= 1
        titles = [e["title"] for e in body["events"]]
        assert sample_world_event.title in titles
