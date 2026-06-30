"""
AI Profile Endpoint Tests

Tests for:
- /api/ai/personas listing (public, optional category filter)
- /api/ai/profile/{ai_id} detail (auth-required, includes posts + intimacy)
- Status label generation (online/offline based on persona local time)
- Auth enforcement on protected endpoints
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_persona import AIPersona


@pytest.mark.asyncio
async def test_list_personas_success(auth_client: AsyncClient, sample_persona):
    """GET /api/ai/personas returns active personas."""
    resp = await auth_client.get("/api/ai/personas")
    assert resp.status_code == 200

    data = resp.json()
    assert "personas" in data
    assert "total" in data
    assert data["total"] >= 1

    names = [p["name"] for p in data["personas"]]
    assert sample_persona.name in names

    # Schema fields exist on each brief entry
    sample_entry = next(p for p in data["personas"] if p["name"] == sample_persona.name)
    for field in ("id", "name", "bio", "profession", "avatar_url",
                  "gender_tag", "category", "archetype"):
        assert field in sample_entry


@pytest.mark.asyncio
async def test_list_personas_filter_by_category(
    auth_client: AsyncClient, db: AsyncSession, sample_persona
):
    """`category` query param filters out personas not in that category."""
    # Add a persona in a different category
    other = AIPersona(
        name="OtherCategoryPersona",
        bio="bio",
        profession="prof",
        personality_prompt="prompt",
        gender_tag="female",
        category="literature",
        archetype="bookworm",
        avatar_url="https://example.com/other.png",
        is_active=1,
        sort_order=2,
    )
    db.add(other)
    await db.commit()

    # Filter by the sample persona's category
    resp = await auth_client.get(
        "/api/ai/personas", params={"category": sample_persona.category}
    )
    assert resp.status_code == 200
    data = resp.json()

    categories = {p["category"] for p in data["personas"]}
    assert categories == {sample_persona.category}
    names = [p["name"] for p in data["personas"]]
    assert "OtherCategoryPersona" not in names
    assert sample_persona.name in names


@pytest.mark.asyncio
async def test_get_persona_detail(
    auth_client: AsyncClient, sample_persona, sample_posts
):
    """GET /api/ai/profile/{ai_id} returns full profile data."""
    resp = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert resp.status_code == 200

    data = resp.json()
    assert data["id"] == sample_persona.id
    assert data["name"] == sample_persona.name
    assert data["bio"] == sample_persona.bio
    assert data["profession"] == sample_persona.profession
    assert data["avatar_url"] == sample_persona.avatar_url
    assert data["gender_tag"] == sample_persona.gender_tag

    # Profile-only fields
    assert "ins_style_tags" in data
    assert "timezone" in data
    assert "status_label" in data
    assert "post_count" in data
    assert "follower_count" in data
    assert "is_following" in data
    assert "intimacy_score" in data
    assert "intimacy_level" in data
    assert "posts" in data

    assert data["post_count"] == len(sample_posts)
    assert isinstance(data["posts"], list)


@pytest.mark.asyncio
async def test_get_persona_not_found(auth_client: AsyncClient):
    """Requesting a non-existent persona returns 404."""
    resp = await auth_client.get("/api/ai/profile/999999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_persona_posts(
    auth_client: AsyncClient, sample_persona, sample_posts
):
    """The profile response includes posts for the persona."""
    resp = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert resp.status_code == 200
    data = resp.json()

    posts = data["posts"]
    assert len(posts) == len(sample_posts)

    # Every post should carry ai_id pointing at the persona, plus required fields
    for post in posts:
        assert post["ai_id"] == sample_persona.id
        assert post["ai_name"] == sample_persona.name
        for field in ("id", "media_url", "caption", "like_count",
                      "is_locked", "is_liked", "is_saved", "created_at"):
            assert field in post

    # Close-friend post should be locked because new user has 0 intimacy
    locked_posts = [p for p in posts if p["is_locked"]]
    assert len(locked_posts) >= 1
    for lp in locked_posts:
        assert lp["media_url"] == ""
        assert lp["caption"] == ""


@pytest.mark.asyncio
async def test_get_persona_posts_empty(auth_client: AsyncClient, sample_persona):
    """A persona with no posts returns an empty posts list and zero post_count."""
    resp = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["posts"] == []
    assert data["post_count"] == 0


@pytest.mark.asyncio
async def test_get_persona_status_online(
    monkeypatch, auth_client: AsyncClient, sample_persona
):
    """Status label reflects an 'online'/working state during daytime hours."""
    # Force the status generator to return a daytime / online label
    monkeypatch.setattr(
        "api.endpoints.ai_profile._generate_status_label",
        lambda tz, profession: "Working",
    )

    resp = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status_label"] == "Working"
    assert data["status_label"] != "Sleeping"


@pytest.mark.asyncio
async def test_get_persona_status_offline(
    monkeypatch, auth_client: AsyncClient, sample_persona
):
    """Status label reflects an offline/sleeping state in late-night hours."""
    monkeypatch.setattr(
        "api.endpoints.ai_profile._generate_status_label",
        lambda tz, profession: "Sleeping",
    )

    resp = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status_label"] == "Sleeping"


@pytest.mark.asyncio
async def test_personas_include_relationship_data(
    auth_client: AsyncClient, sample_persona
):
    """Profile response includes intimacy + follow relationship data."""
    resp = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert resp.status_code == 200
    data = resp.json()

    # Relationship fields exist
    assert "intimacy_score" in data
    assert "intimacy_level" in data
    assert "is_following" in data
    assert "follower_count" in data

    # A brand-new auth user has no interaction yet -> defaults
    assert data["intimacy_score"] == 0.0
    assert data["intimacy_level"] == "Stranger"
    assert data["is_following"] is False
    assert isinstance(data["follower_count"], int)

    # Follow the persona and confirm is_following flips to True
    follow_resp = await auth_client.post(f"/api/ai/{sample_persona.id}/follow")
    assert follow_resp.status_code == 200
    assert follow_resp.json()["following"] is True

    resp2 = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert resp2.status_code == 200
    assert resp2.json()["is_following"] is True


@pytest.mark.asyncio
async def test_personas_unauthenticated(client: AsyncClient, sample_persona):
    """Auth-protected profile endpoint returns 401 without a token."""
    resp = await client.get(f"/api/ai/profile/{sample_persona.id}")
    assert resp.status_code == 401
