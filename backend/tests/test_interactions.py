"""
Interactions Endpoint Tests

Covers:
- GET /api/interactions/summary       (intimacy + last-chat summary)
- POST /api/ai/{ai_id}/follow         (follow persona, idempotent)
- DELETE /api/ai/{ai_id}/follow       (unfollow persona, idempotent)
- GET /api/ai/profile/{ai_id}         (follower_count + is_following surface)

Authentication and 404 edge cases are also asserted.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_persona import AIPersona
from models.chat_message import ChatMessage
from models.follow import Follow
from models.interaction import Interaction
from models.user import User


AUTH_EMAIL = "testuser@example.com"


async def _get_auth_user(db: AsyncSession) -> User:
    """Resolve the User registered by the ``auth_client`` fixture."""
    result = await db.execute(select(User).where(User.email == AUTH_EMAIL))
    user = result.scalar_one_or_none()
    assert user is not None, "auth_client fixture must register a user first"
    return user


@pytest.mark.asyncio
async def test_get_interaction_data(
    auth_client: AsyncClient,
    db: AsyncSession,
    sample_persona: AIPersona,
):
    """GET /api/interactions/summary returns intimacy & stats for the user."""
    user = await _get_auth_user(db)

    db.add(Interaction(
        user_id=user.id,
        ai_id=sample_persona.id,
        intimacy_score=5.5,
        last_chat_summary="They talked about music.",
        streak_count=2,
        total_interaction_days=4,
    ))
    await db.commit()

    resp = await auth_client.get("/api/interactions/summary")
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list)

    entry = next((e for e in data if e["ai_id"] == sample_persona.id), None)
    assert entry is not None
    assert entry["ai_name"] == sample_persona.name
    assert entry["avatar_url"] == sample_persona.avatar_url
    assert entry["intimacy_score"] == pytest.approx(5.5)
    assert entry["intimacy_level"] == "friend"
    assert "last_chat_at" in entry


@pytest.mark.asyncio
async def test_get_interaction_new_user(client: AsyncClient):
    """A freshly-registered user with no Interaction rows gets an empty list.

    Uses a brand-new account (independent of ``auth_client``) so leakage from
    other tests sharing the session-scoped engine cannot pollute the result.
    """
    email = "new_interaction_user@example.com"
    await client.post("/api/auth/register", json={
        "email": email,
        "password": "TestPass123!",
        "nickname": "NewInteractionUser",
    })
    login = await client.post(
        "/api/auth/login",
        data={"username": email, "password": "TestPass123!"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]

    resp = await client.get(
        "/api/interactions/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_follow_persona_success(
    auth_client: AsyncClient,
    db: AsyncSession,
    sample_persona: AIPersona,
):
    """POST /api/ai/{ai_id}/follow creates a Follow row."""
    resp = await auth_client.post(f"/api/ai/{sample_persona.id}/follow")

    assert resp.status_code == 200
    assert resp.json() == {"following": True}

    user = await _get_auth_user(db)
    result = await db.execute(
        select(Follow).where(
            Follow.user_id == user.id,
            Follow.ai_id == sample_persona.id,
        )
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_follow_persona_idempotent(
    auth_client: AsyncClient,
    db: AsyncSession,
    sample_persona: AIPersona,
):
    """Calling follow twice succeeds without creating duplicate rows."""
    first = await auth_client.post(f"/api/ai/{sample_persona.id}/follow")
    second = await auth_client.post(f"/api/ai/{sample_persona.id}/follow")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == {"following": True}
    assert second.json() == {"following": True}

    user = await _get_auth_user(db)
    result = await db.execute(
        select(Follow).where(
            Follow.user_id == user.id,
            Follow.ai_id == sample_persona.id,
        )
    )
    follows = result.scalars().all()
    assert len(follows) == 1


@pytest.mark.asyncio
async def test_unfollow_persona_success(
    auth_client: AsyncClient,
    db: AsyncSession,
    sample_persona: AIPersona,
):
    """DELETE /api/ai/{ai_id}/follow removes the existing Follow row."""
    user = await _get_auth_user(db)
    db.add(Follow(user_id=user.id, ai_id=sample_persona.id))
    await db.commit()

    resp = await auth_client.delete(f"/api/ai/{sample_persona.id}/follow")

    assert resp.status_code == 200
    assert resp.json() == {"following": False}

    result = await db.execute(
        select(Follow).where(
            Follow.user_id == user.id,
            Follow.ai_id == sample_persona.id,
        )
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_unfollow_persona_not_followed(
    auth_client: AsyncClient,
    sample_persona: AIPersona,
):
    """Unfollowing a persona that was never followed is a no-op (200)."""
    resp = await auth_client.delete(f"/api/ai/{sample_persona.id}/follow")

    assert resp.status_code == 200
    assert resp.json() == {"following": False}


@pytest.mark.asyncio
async def test_follow_increments_follower_count(
    auth_client: AsyncClient,
    sample_persona: AIPersona,
):
    """follower_count surfaced by /api/ai/profile/{ai_id} updates after follow."""
    before = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert before.status_code == 200
    base_count = before.json()["follower_count"]
    assert before.json()["is_following"] is False

    follow_resp = await auth_client.post(f"/api/ai/{sample_persona.id}/follow")
    assert follow_resp.status_code == 200

    after = await auth_client.get(f"/api/ai/profile/{sample_persona.id}")
    assert after.status_code == 200
    assert after.json()["follower_count"] == base_count + 1
    assert after.json()["is_following"] is True


@pytest.mark.asyncio
async def test_interaction_requires_auth(
    client: AsyncClient,
    sample_persona: AIPersona,
):
    """Interaction + follow endpoints reject anonymous callers with 401."""
    resp = await client.get("/api/interactions/summary")
    assert resp.status_code == 401

    follow_resp = await client.post(f"/api/ai/{sample_persona.id}/follow")
    assert follow_resp.status_code == 401


@pytest.mark.asyncio
async def test_interaction_invalid_ai_id(auth_client: AsyncClient):
    """Profile lookup for a non-existent AI persona returns 404."""
    resp = await auth_client.get("/api/ai/profile/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_intimacy_reflects_chat_history(
    auth_client: AsyncClient,
    db: AsyncSession,
    sample_persona: AIPersona,
):
    """High intimacy_score maps to 'soulmate' and last_chat_at is populated."""
    user = await _get_auth_user(db)

    db.add(Interaction(
        user_id=user.id,
        ai_id=sample_persona.id,
        intimacy_score=9.0,
        last_chat_summary="deep conversation",
        streak_count=10,
        total_interaction_days=20,
    ))
    db.add(ChatMessage(
        user_id=user.id,
        ai_id=sample_persona.id,
        role="user",
        content="hello",
        message_type="chat",
    ))
    await db.commit()

    resp = await auth_client.get("/api/interactions/summary")
    assert resp.status_code == 200

    data = resp.json()
    # Other tests may share the session-scoped engine; filter to this persona.
    entry = next((e for e in data if e["ai_id"] == sample_persona.id), None)
    assert entry is not None
    assert entry["intimacy_score"] == pytest.approx(9.0)
    assert entry["intimacy_level"] == "soulmate"
    assert entry["last_chat_at"]
