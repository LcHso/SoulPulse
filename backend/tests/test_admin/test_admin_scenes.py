"""Admin scenes endpoint tests."""

import pytest
from httpx import AsyncClient


class TestAdminScenes:
    """Tests for ``/api/admin/scenes/*`` endpoints."""

    @pytest.mark.asyncio
    async def test_list_scenes(self, admin_client: AsyncClient, sample_scene):
        """GET /scenes/ returns paginated scenes including the seeded one."""
        resp = await admin_client.get(
            "/api/admin/scenes/", params={"persona_id": sample_scene.persona_id}
        )
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert {"scenes", "total", "page", "page_size", "total_pages"}.issubset(
            body.keys()
        )
        assert body["total"] >= 1
        scene_names = [s["scene_name"] for s in body["scenes"]]
        assert sample_scene.scene_name in scene_names

    @pytest.mark.asyncio
    async def test_create_scene(self, admin_client: AsyncClient, sample_persona):
        """POST /scenes/ creates a new scene."""
        payload = {
            "persona_id": sample_persona.id,
            "scene_name": "深夜电话",
            "scene_type": "emotional_support",
            "setting_description": "凌晨两点，你拨通了他的电话。",
            "system_prompt_addon": "你被深夜的来电叫醒，声音带着睡意但温柔。",
            "mood_preset": "intimate",
            "required_intimacy": 10,
            "unlock_type": "free",
            "max_messages": 25,
            "is_active": True,
            "sort_order": 5,
        }
        resp = await admin_client.post("/api/admin/scenes/", json=payload)
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["scene_name"] == "深夜电话"
        assert data["scene_type"] == "emotional_support"
        assert data["max_messages"] == 25
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_update_scene(self, admin_client: AsyncClient, sample_scene):
        """PUT /scenes/{id} updates editable fields."""
        resp = await admin_client.put(
            f"/api/admin/scenes/{sample_scene.id}",
            json={"scene_name": "雨夜咖啡馆", "required_intimacy": 20},
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert data["scene_name"] == "雨夜咖啡馆"
        assert data["required_intimacy"] == 20
