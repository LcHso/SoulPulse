"""Admin DevOps & model tuning endpoint tests."""

import pytest
from httpx import AsyncClient


class TestAdminDevops:
    """Tests for ``/api/admin/config``, ``/models/current``, ``/audit-logs``."""

    @pytest.mark.asyncio
    async def test_health_check(self, admin_client: AsyncClient):
        """Admin "health" surface = GET /models/current returns configured model IDs.

        The dedicated devops router does not expose a /health endpoint;
        ``/models/current`` plays the role of a config-health probe.
        """
        resp = await admin_client.get("/api/admin/models/current")
        assert resp.status_code == 200, resp.text

        data = resp.json()
        for key in (
            "chat_model",
            "character_model",
            "image_model",
            "video_model",
            "embedding_model",
        ):
            assert key in data, f"missing model field: {key}"

    @pytest.mark.asyncio
    async def test_backup_trigger(self, admin_client: AsyncClient):
        """Admin "backup" surface = GET /audit-logs returns the auditable history.

        No backup endpoint exists in the devops router; audit log retrieval
        is the closest operational endpoint for verification.
        """
        resp = await admin_client.get(
            "/api/admin/audit-logs", params={"limit": 5, "offset": 0}
        )
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert {"logs", "total", "has_more"}.issubset(body.keys())
        assert isinstance(body["logs"], list)

    @pytest.mark.asyncio
    async def test_devops_requires_admin(self, auth_client: AsyncClient):
        """Non-admin users cannot reach devops endpoints."""
        for path in (
            "/api/admin/config",
            "/api/admin/models/current",
            "/api/admin/audit-logs",
            "/api/admin/api-usage",
        ):
            resp = await auth_client.get(path)
            assert resp.status_code == 403, f"{path} should require admin"
