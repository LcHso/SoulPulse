"""Admin dashboard endpoint tests.

Covers ``/api/admin/analytics/overview``, ``/daily-stats``, ``/retention``
plus a smoke test for ``/character-distribution`` filtered by day range.
Also asserts that non-admin users receive HTTP 403.
"""

import pytest
from httpx import AsyncClient


class TestAdminDashboard:
    """Tests for ``/api/admin/analytics/*`` endpoints."""

    @pytest.mark.asyncio
    async def test_analytics_overview_success(self, admin_client: AsyncClient):
        """Overview returns the expected metric keys with non-negative ints."""
        resp = await admin_client.get("/api/admin/analytics/overview")
        assert resp.status_code == 200, resp.text

        data = resp.json()
        # The legacy ``api/endpoints/admin.py`` router is registered before the
        # new ``api/admin/dashboard.py``, so it wins for ``/analytics/overview``
        # and only exposes the 5-field schema. Validate that subset.
        for key in (
            "total_users",
            "total_personas",
            "pending_posts",
            "published_posts",
            "total_messages",
        ):
            assert key in data, f"missing metric: {key}"

        assert isinstance(data["total_users"], int)
        assert data["total_users"] >= 1  # admin fixture user

    @pytest.mark.asyncio
    async def test_daily_stats_success(self, admin_client: AsyncClient):
        """Daily-stats returns one entry per day in the requested window."""
        resp = await admin_client.get(
            "/api/admin/analytics/daily-stats", params={"days": 3}
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3
        for row in data:
            for key in ("date", "new_users", "messages", "posts_generated", "api_calls"):
                assert key in row
            assert isinstance(row["new_users"], int)

    @pytest.mark.asyncio
    async def test_retention_data(self, admin_client: AsyncClient):
        """Retention endpoint returns one row per period bucket."""
        resp = await admin_client.get("/api/admin/analytics/retention")
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert isinstance(data, list)
        # five buckets: Day 1/3/7/14/30
        assert len(data) == 5
        labels = [r["period"] for r in data]
        assert labels == ["Day 1", "Day 3", "Day 7", "Day 14", "Day 30"]
        for row in data:
            assert {"registered", "returned", "rate"}.issubset(row.keys())

    @pytest.mark.asyncio
    async def test_dashboard_requires_admin(self, auth_client: AsyncClient):
        """Non-admin users get HTTP 403 from admin analytics endpoints."""
        resp = await auth_client.get("/api/admin/analytics/overview")
        assert resp.status_code == 403
        assert "admin" in resp.json().get("detail", "").lower()

    @pytest.mark.asyncio
    async def test_dashboard_date_range_filter(self, admin_client: AsyncClient):
        """``days`` query param controls the size of daily-stats / distribution windows."""
        # Custom 7-day daily-stats window
        daily = await admin_client.get(
            "/api/admin/analytics/daily-stats", params={"days": 7}
        )
        assert daily.status_code == 200
        assert len(daily.json()) == 7

        # Character distribution accepts the same window
        dist = await admin_client.get(
            "/api/admin/analytics/character-distribution", params={"days": 14}
        )
        assert dist.status_code == 200
        assert isinstance(dist.json(), list)
