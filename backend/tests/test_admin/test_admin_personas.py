"""Admin persona / soul-lab endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestAdminPersonas:
    """Tests for ``/api/admin/personas*`` endpoints."""

    @pytest.mark.asyncio
    async def test_list_personas(self, admin_client: AsyncClient, sample_persona):
        """Persona listing includes the seeded persona."""
        resp = await admin_client.get("/api/admin/personas")
        assert resp.status_code == 200, resp.text

        personas = resp.json()
        assert isinstance(personas, list)
        names = [p["name"] for p in personas]
        assert sample_persona.name in names

    @pytest.mark.asyncio
    async def test_create_persona(
        self, admin_client: AsyncClient, db: AsyncSession
    ):
        """No POST /personas endpoint exists; admin lists reflect direct DB inserts.

        This mirrors the production workflow where personas are seeded via
        scripts/seed.py rather than the admin REST API.
        """
        from models.ai_persona import AIPersona

        persona = AIPersona(
            name="测试新角色",
            bio="A newly seeded test persona.",
            profession="设计师",
            personality_prompt="你是一位严谨的设计师。",
            gender_tag="female",
            category="gl",
            archetype="冷静理性",
            avatar_url="https://example.com/avatars/new.png",
            is_active=1,
            sort_order=99,
        )
        db.add(persona)
        await db.commit()
        await db.refresh(persona)

        # Verify it surfaces in the admin listing
        resp = await admin_client.get("/api/admin/personas")
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert "测试新角色" in names

    @pytest.mark.asyncio
    async def test_update_persona(
        self, admin_client: AsyncClient, sample_persona, db: AsyncSession
    ):
        """PUT /personas/{id} updates editable fields.

        Only fields supported by the legacy ``PersonaUpdateRequest`` (which
        wins the route over the new admin router) are exercised here.
        """
        new_bio = "更新后的简介内容"
        new_avatar = "https://example.com/avatars/updated.png"
        resp = await admin_client.put(
            f"/api/admin/personas/{sample_persona.id}",
            json={"bio": new_bio, "avatar_url": new_avatar},
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["bio"] == new_bio
        assert data["avatar_url"] == new_avatar

        # Confirm persistence. Use ``populate_existing=True`` so the identity-map
        # cached copy is refreshed from the row written by the API session.
        from models.ai_persona import AIPersona

        refreshed = (
            await db.execute(
                select(AIPersona)
                .where(AIPersona.id == sample_persona.id)
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        assert refreshed.bio == new_bio

    @pytest.mark.asyncio
    async def test_publish_persona(
        self, admin_client: AsyncClient, sample_persona
    ):
        """Toggling ``is_active`` via update endpoint controls publication."""
        # Deactivate
        off = await admin_client.put(
            f"/api/admin/personas/{sample_persona.id}",
            json={"is_active": 0},
        )
        assert off.status_code == 200
        assert off.json()["is_active"] == 0

        # Reactivate
        on = await admin_client.put(
            f"/api/admin/personas/{sample_persona.id}",
            json={"is_active": 1},
        )
        assert on.status_code == 200
        assert on.json()["is_active"] == 1

    @pytest.mark.asyncio
    async def test_persona_requires_admin(
        self, auth_client: AsyncClient, sample_persona
    ):
        """Regular users cannot list or update personas via admin API."""
        list_resp = await auth_client.get("/api/admin/personas")
        assert list_resp.status_code == 403

        update_resp = await auth_client.put(
            f"/api/admin/personas/{sample_persona.id}",
            json={"bio": "hacked"},
        )
        assert update_resp.status_code == 403
