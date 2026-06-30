"""
E2E User Journey Tests

Tests that exercise multi-endpoint user flows: registration → persona
discovery → social interactions → subscription purchase.  External APIs
are mocked; internal services run against in-memory SQLite.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.interaction import Interaction
from models.follow import Follow
from models.user_like import UserLike
from models.comment import Comment
from models.subscription import SubscriptionTier, UserSubscription
from models.user import User


# ─── Helpers ────────────────────────────────────────────────────────────────


async def _register_and_login(client: AsyncClient, email: str, password: str, nickname: str) -> str:
    """Register a new user and return the JWT access token."""
    await client.post("/api/auth/register", json={
        "email": email,
        "password": password,
        "nickname": nickname,
    })
    login_resp = await client.post("/api/auth/login", data={
        "username": email,
        "password": password,
    })
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    return login_resp.json()["access_token"]


# ─── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_new_user_onboarding(
    client: AsyncClient,
    db: AsyncSession,
    sample_persona,
    mock_ai_service,
    mock_vector_store,
):
    """
    New user onboarding: Register → list personas → follow a persona →
    send first message → verify interaction record created.
    """
    # 1. Register & login
    token = await _register_and_login(client, "onboard@test.com", "Pass123!", "NewUser")
    headers = {"Authorization": f"Bearer {token}"}

    # 2. List personas
    personas_resp = await client.get("/api/ai/personas", headers=headers)
    assert personas_resp.status_code == 200
    personas_data = personas_resp.json()
    assert "personas" in personas_data
    assert len(personas_data["personas"]) > 0

    # Verify our sample persona is in the list
    persona_ids = [p["id"] for p in personas_data["personas"]]
    assert sample_persona.id in persona_ids

    # 3. Follow the persona
    follow_resp = await client.post(
        f"/api/ai/{sample_persona.id}/follow",
        headers=headers,
    )
    assert follow_resp.status_code == 200
    assert follow_resp.json()["following"] is True

    # Verify follow record in DB
    me_resp = await client.get("/api/auth/me", headers=headers)
    user_id = me_resp.json()["id"]

    follow_result = await db.execute(
        select(Follow).where(
            Follow.user_id == user_id,
            Follow.ai_id == sample_persona.id,
        )
    )
    assert follow_result.scalar_one_or_none() is not None, "Follow record should exist"

    # 4. Send first message
    chat_resp = await client.post("/api/chat/send", json={
        "ai_id": sample_persona.id,
        "message": "你好！我刚来到这里，很高兴认识你！",
    }, headers=headers)
    assert chat_resp.status_code == 200
    assert len(chat_resp.json()["reply"]) > 0

    # 5. Verify interaction record was created
    interaction_result = await db.execute(
        select(Interaction).where(
            Interaction.user_id == user_id,
            Interaction.ai_id == sample_persona.id,
        )
    )
    interaction = interaction_result.scalar_one_or_none()
    assert interaction is not None, "Interaction record should exist after first chat"
    assert interaction.intimacy_score > 0, "Intimacy should be positive after chat"


@pytest.mark.asyncio
async def test_social_interaction_flow(
    client: AsyncClient,
    db: AsyncSession,
    sample_persona,
    sample_posts,
    mock_ai_service,
    mock_vector_store,
):
    """
    Social interaction flow: View feed posts → like a post → post a
    comment → verify like count incremented.
    """
    # Register & login
    token = await _register_and_login(client, "social@test.com", "Pass123!", "SocialUser")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. View feed posts
    feed_resp = await client.get("/api/feed/posts", headers=headers)
    assert feed_resp.status_code == 200
    posts = feed_resp.json()
    # sample_posts has 3 posts (is_close_friend=False for posts 1,2; True for post 3)
    # Post 3 is close_friend, so it might be filtered. At least 2 should be visible.
    assert len(posts) >= 2, f"Expected at least 2 visible posts, got {len(posts)}"

    # Pick the first post to interact with
    target_post = posts[0]
    post_id = target_post["id"]
    original_like_count = target_post["like_count"]

    # 2. Like the post
    like_resp = await client.post(
        f"/api/feed/posts/{post_id}/like",
        headers=headers,
    )
    assert like_resp.status_code == 200
    like_data = like_resp.json()
    assert like_data["status"] == "liked"
    assert like_data["like_count"] == original_like_count + 1

    # Verify like record in DB
    me_resp = await client.get("/api/auth/me", headers=headers)
    user_id = me_resp.json()["id"]

    like_result = await db.execute(
        select(UserLike).where(
            UserLike.user_id == user_id,
            UserLike.post_id == post_id,
        )
    )
    assert like_result.scalar_one_or_none() is not None, "Like record should exist"

    # 3. Post a comment (the delayed AI reply runs as a background task;
    #    we don't need to wait for it - just verify immediate effects)
    comment_resp = await client.post(
        f"/api/feed/posts/{post_id}/comments",
        json={"content": "这张照片拍得真好看！"},
        headers=headers,
    )
    assert comment_resp.status_code == 200
    comment_data = comment_resp.json()
    assert comment_data["content"] == "这张照片拍得真好看！"
    assert comment_data["is_ai_reply"] is False

    # 4. Verify comment exists in DB
    comment_result = await db.execute(
        select(Comment).where(
            Comment.user_id == user_id,
            Comment.post_id == post_id,
        )
    )
    comment = comment_result.scalar_one_or_none()
    assert comment is not None, "Comment should be persisted"
    assert comment.content == "这张照片拍得真好看！"

    # 5. Verify like count was incremented by re-fetching the post
    post_detail_resp = await client.get(
        f"/api/feed/posts/{post_id}",
        headers=headers,
    )
    assert post_detail_resp.status_code == 200
    assert post_detail_resp.json()["like_count"] == original_like_count + 1
    assert post_detail_resp.json()["is_liked"] is True


@pytest.mark.asyncio
async def test_subscription_purchase_flow(
    client: AsyncClient,
    db: AsyncSession,
    mock_ai_service,
    mock_vector_store,
):
    """
    Subscription purchase flow: Create tier → register user with gems →
    list tiers → subscribe → verify subscription active → verify gem
    balance reduced.
    """
    # 1. Create a subscription tier in the DB
    tier = SubscriptionTier(
        tier_name="vip",
        display_name="VIP月卡",
        price_gems=100,
        duration_days=30,
        benefits_json={"daily_gems": 5, "hd_images": True, "priority_dm": True},
        is_active=True,
        sort_order=1,
    )
    db.add(tier)
    await db.commit()
    await db.refresh(tier)

    # 2. Register user
    token = await _register_and_login(client, "subscriber@test.com", "Pass123!", "SubUser")
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Get user info and give them gems
    me_resp = await client.get("/api/auth/me", headers=headers)
    user_id = me_resp.json()["id"]

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one()
    user.gem_balance = 500
    await db.commit()

    # 4. List tiers - verify our tier is visible
    tiers_resp = await client.get("/api/subscription/tiers", headers=headers)
    assert tiers_resp.status_code == 200
    tiers_data = tiers_resp.json()
    tier_ids = [t["id"] for t in tiers_data]
    assert tier.id in tier_ids, "Created tier should appear in tier list"

    # 5. Subscribe
    sub_resp = await client.post(
        f"/api/subscription/subscribe/{tier.id}",
        headers=headers,
    )
    assert sub_resp.status_code == 200, f"Subscribe failed: {sub_resp.text}"
    sub_data = sub_resp.json()
    assert sub_data["tier"] == "vip"
    assert sub_data["gems_charged"] == 100
    assert sub_data["remaining_balance"] == 400

    # 6. Verify subscription is active
    status_resp = await client.get("/api/subscription/my-subscription", headers=headers)
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["active"] is True
    assert status_data["tier"] == "vip"

    # 7. Verify gem balance in DB
    await db.refresh(user)
    assert user.gem_balance == 400, f"Expected 400 gems, got {user.gem_balance}"

    # 8. Verify UserSubscription record exists
    sub_result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user_id,
            UserSubscription.tier_id == tier.id,
            UserSubscription.is_active.is_(True),
        )
    )
    subscription = sub_result.scalar_one_or_none()
    assert subscription is not None, "UserSubscription record should exist"
    assert subscription.expires_at is not None
