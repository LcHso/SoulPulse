"""Admin users / trust & safety endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestAdminUsers:
    """Tests for ``/api/admin/users*`` endpoints."""

    @pytest.mark.asyncio
    async def test_list_users(self, admin_client: AsyncClient, sample_user):
        """List endpoint returns user data including the seeded user.

        Note: the legacy ``api/endpoints/admin.py`` router is registered before
        ``api/admin/users.py`` in ``main.py``, so it wins this path and returns
        a bare ``list[UserOut]`` instead of the paginated dict.
        """
        resp = await admin_client.get("/api/admin/users", params={"limit": 10, "offset": 0})
        assert resp.status_code == 200, resp.text

        data = resp.json()
        # Legacy endpoint returns a bare list; new endpoint returns a dict.
        if isinstance(data, dict):
            assert {"users", "total", "has_more"}.issubset(data.keys())
            assert data["total"] >= 2  # admin + sample_user
            users_list = data["users"]
        else:
            assert isinstance(data, list)
            assert len(data) >= 2
            users_list = data
        emails = [u["email"] for u in users_list]
        assert sample_user.email in emails

    @pytest.mark.asyncio
    async def test_get_user_detail(self, admin_client: AsyncClient, sample_user):
        """Per-user detail returns profile + message aggregates."""
        resp = await admin_client.get(f"/api/admin/users/{sample_user.id}")
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["id"] == sample_user.id
        assert data["email"] == sample_user.email
        assert "total_messages" in data
        assert "persona_interactions" in data
        assert isinstance(data["persona_interactions"], list)

    @pytest.mark.asyncio
    async def test_ban_user(
        self, admin_client: AsyncClient, sample_user, db: AsyncSession
    ):
        """Banning a user records a moderation entry with action_taken=ban."""
        from models.content_moderation_log import ContentModerationLog

        resp = await admin_client.post(
            f"/api/admin/users/{sample_user.id}/ban",
            params={"reason": "spam"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["user_id"] == sample_user.id

        result = await db.execute(
            select(ContentModerationLog).where(
                ContentModerationLog.user_id == sample_user.id,
                ContentModerationLog.action_taken == "ban",
            )
        )
        ban_entry = result.scalar_one_or_none()
        assert ban_entry is not None
        assert ban_entry.reason == "spam"

    @pytest.mark.asyncio
    async def test_unban_user(
        self, admin_client: AsyncClient, sample_user, db: AsyncSession
    ):
        """Unbanning records a moderation entry with action_taken=unban."""
        from models.content_moderation_log import ContentModerationLog

        # First ban, then unban
        await admin_client.post(f"/api/admin/users/{sample_user.id}/ban")
        resp = await admin_client.post(f"/api/admin/users/{sample_user.id}/unban")
        assert resp.status_code == 200, resp.text

        result = await db.execute(
            select(ContentModerationLog).where(
                ContentModerationLog.user_id == sample_user.id,
                ContentModerationLog.action_taken == "unban",
            )
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_ban_creates_audit_log(
        self, admin_client: AsyncClient, sample_user, db: AsyncSession
    ):
        """The ban action persists a ContentModerationLog row attributed to the admin."""
        from models.content_moderation_log import ContentModerationLog
        from models.user import User

        before_result = await db.execute(
            select(ContentModerationLog).where(
                ContentModerationLog.content_type == "user_ban",
                ContentModerationLog.user_id == sample_user.id,
            )
        )
        before_count = len(before_result.scalars().all())

        resp = await admin_client.post(
            f"/api/admin/users/{sample_user.id}/ban",
            params={"reason": "tos-violation"},
        )
        assert resp.status_code == 200, resp.text

        after_result = await db.execute(
            select(ContentModerationLog).where(
                ContentModerationLog.content_type == "user_ban",
                ContentModerationLog.user_id == sample_user.id,
            )
        )
        logs = after_result.scalars().all()
        assert len(logs) == before_count + 1

        # The reviewer_id must reference an existing admin user
        admin_row = (
            await db.execute(select(User).where(User.id == logs[-1].reviewer_id))
        ).scalar_one()
        assert admin_row.is_admin == 1

    @pytest.mark.asyncio
    async def test_non_admin_rejected(
        self, auth_client: AsyncClient, sample_user
    ):
        """Regular authenticated users cannot reach admin user endpoints."""
        list_resp = await auth_client.get("/api/admin/users")
        assert list_resp.status_code == 403

        ban_resp = await auth_client.post(
            f"/api/admin/users/{sample_user.id}/ban"
        )
        assert ban_resp.status_code == 403
