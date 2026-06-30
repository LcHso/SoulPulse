"""Admin memory & cognitive management endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestAdminMemory:
    """Tests for ``/api/admin/memories*`` endpoints."""

    @pytest.mark.asyncio
    async def test_search_memories(
        self, admin_client: AsyncClient, sample_memory
    ):
        """GET /memories returns the listing envelope filtered by user/ai."""
        resp = await admin_client.get(
            "/api/admin/memories",
            params={"user_id": sample_memory.user_id, "ai_id": sample_memory.ai_id},
        )
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert {"memories", "total", "has_more"}.issubset(body.keys())
        assert body["total"] >= 1
        contents = [m["content"] for m in body["memories"]]
        assert sample_memory.content in contents

    @pytest.mark.asyncio
    async def test_delete_memory(
        self, admin_client: AsyncClient, sample_memory, db: AsyncSession
    ):
        """DELETE /memories/{id} removes the row."""
        from models.memory_entry import MemoryEntry

        resp = await admin_client.delete(
            f"/api/admin/memories/{sample_memory.id}"
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["id"] == sample_memory.id

        # Confirm DB row is gone
        result = await db.execute(
            select(MemoryEntry).where(MemoryEntry.id == sample_memory.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_memory_requires_admin(
        self, auth_client: AsyncClient, sample_memory
    ):
        """Non-admin users cannot list or delete memories."""
        list_resp = await auth_client.get("/api/admin/memories")
        assert list_resp.status_code == 403

        del_resp = await auth_client.delete(
            f"/api/admin/memories/{sample_memory.id}"
        )
        assert del_resp.status_code == 403
