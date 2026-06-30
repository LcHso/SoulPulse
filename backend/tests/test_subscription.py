"""
Subscription Endpoint Tests

Covers /api/subscription/* user-facing routes:
- GET    /api/subscription/tiers              (list active tiers)
- GET    /api/subscription/my-subscription    (current status)
- POST   /api/subscription/subscribe/{tier_id}(subscribe / renew / upgrade)

Validates tier catalog surface, subscription lifecycle (create/upgrade/expire),
gem-balance deduction, and unauthenticated access guards.
"""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.gem_transaction import GemTransaction
from models.subscription import SubscriptionTier, UserSubscription
from models.user import User


AUTH_EMAIL = "testuser@example.com"


async def _get_auth_user(db: AsyncSession) -> User:
    """Resolve the User registered by the ``auth_client`` fixture."""
    result = await db.execute(select(User).where(User.email == AUTH_EMAIL))
    user = result.scalar_one_or_none()
    assert user is not None, "auth_client fixture must register a user first"
    return user


async def _reset_subscription_state(db: AsyncSession) -> None:
    """Wipe subscription/tier/transaction rows so each test sees a clean DB.

    The ``engine`` fixture is session-scoped, so committed rows from one test
    leak into the next. We clear the subscription-related tables explicitly
    at the start of each test that depends on counts.
    """
    await db.execute(delete(GemTransaction))
    await db.execute(delete(UserSubscription))
    await db.execute(delete(SubscriptionTier))
    await db.commit()


async def _seed_tiers(db: AsyncSession) -> dict[str, SubscriptionTier]:
    """Seed a small, deterministic tier catalog and return it by name."""
    await _reset_subscription_state(db)
    free_tier = SubscriptionTier(
        tier_name="free",
        display_name="Free",
        price_gems=0,
        duration_days=30,
        benefits_json={"daily_gems": 0},
        is_active=True,
        sort_order=0,
    )
    vip_tier = SubscriptionTier(
        tier_name="vip",
        display_name="VIP月卡",
        price_gems=50,
        duration_days=30,
        benefits_json={
            "daily_gems": 10,
            "hd_images": True,
            "priority_dm": True,
        },
        is_active=True,
        sort_order=1,
    )
    svip_tier = SubscriptionTier(
        tier_name="svip",
        display_name="SVIP月卡",
        price_gems=80,
        duration_days=30,
        benefits_json={
            "daily_gems": 25,
            "hd_images": True,
            "priority_dm": True,
            "exclusive_scenes": True,
            "unlimited_replay": True,
        },
        is_active=True,
        sort_order=2,
    )
    inactive_tier = SubscriptionTier(
        tier_name="legacy",
        display_name="Legacy (hidden)",
        price_gems=10,
        duration_days=30,
        benefits_json={},
        is_active=False,
        sort_order=99,
    )
    db.add_all([free_tier, vip_tier, svip_tier, inactive_tier])
    await db.commit()
    for t in (free_tier, vip_tier, svip_tier, inactive_tier):
        await db.refresh(t)
    return {
        "free": free_tier,
        "vip": vip_tier,
        "svip": svip_tier,
        "legacy": inactive_tier,
    }


# ── GET /tiers ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tiers_success(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """GET /api/subscription/tiers returns all active tiers ordered."""
    tiers = await _seed_tiers(db)

    resp = await auth_client.get("/api/subscription/tiers")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert isinstance(data, list)
    names = [t["tier_name"] for t in data]
    # Inactive tier must be hidden, active tiers ordered by sort_order
    assert "legacy" not in names
    assert names == ["free", "vip", "svip"]

    vip_payload = next(t for t in data if t["tier_name"] == "vip")
    assert vip_payload["display_name"] == tiers["vip"].display_name
    assert vip_payload["price_gems"] == 50
    assert vip_payload["duration_days"] == 30
    assert vip_payload["benefits"]["hd_images"] is True


# ── POST /subscribe/{tier_id} ──────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_success(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """POST /subscribe/{tier_id} creates an active UserSubscription row."""
    tiers = await _seed_tiers(db)
    user = await _get_auth_user(db)
    user.gem_balance = 200
    await db.commit()

    resp = await auth_client.post(f"/api/subscription/subscribe/{tiers['vip'].id}")
    assert resp.status_code == 200, resp.text

    payload = resp.json()
    assert payload["tier"] == "vip"
    assert payload["gems_charged"] == 50
    assert payload["remaining_balance"] == 150
    assert "expires_at" in payload

    # Persisted UserSubscription exists and is active.
    sub_res = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    subs = sub_res.scalars().all()
    assert len(subs) == 1
    assert subs[0].tier_id == tiers["vip"].id
    assert subs[0].is_active is True
    assert subs[0].expires_at > datetime.utcnow() + timedelta(days=29)


@pytest.mark.asyncio
async def test_subscribe_insufficient_gems(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """Returns 400 when the user cannot afford the tier."""
    tiers = await _seed_tiers(db)
    user = await _get_auth_user(db)
    user.gem_balance = 10  # below vip(50)
    await db.commit()

    resp = await auth_client.post(f"/api/subscription/subscribe/{tiers['vip'].id}")
    assert resp.status_code == 400
    assert "insufficient" in resp.json()["detail"].lower()

    # No subscription should have been created.
    sub_res = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    assert sub_res.scalar_one_or_none() is None
    # Balance untouched.
    await db.refresh(user)
    assert user.gem_balance == 10


@pytest.mark.asyncio
async def test_subscribe_unauthenticated(client: AsyncClient, db: AsyncSession):
    """Without a valid token, /subscribe returns 401."""
    tiers = await _seed_tiers(db)
    resp = await client.post(f"/api/subscription/subscribe/{tiers['vip'].id}")
    assert resp.status_code == 401


# ── GET /my-subscription ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_status_no_subscription(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """Without any UserSubscription row the status is the free/inactive tier."""
    await _seed_tiers(db)

    resp = await auth_client.get("/api/subscription/my-subscription")
    assert resp.status_code == 200, resp.text

    data = resp.json()
    assert data["tier"] == "free"
    assert data["active"] is False
    assert data["tier_id"] is None
    assert data["expires_at"] is None
    assert data["benefits"] == {}


@pytest.mark.asyncio
async def test_get_status_active(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """Active subscription is surfaced with tier metadata + benefits."""
    tiers = await _seed_tiers(db)
    user = await _get_auth_user(db)
    user.gem_balance = 500
    await db.commit()

    sub_resp = await auth_client.post(
        f"/api/subscription/subscribe/{tiers['svip'].id}"
    )
    assert sub_resp.status_code == 200

    resp = await auth_client.get("/api/subscription/my-subscription")
    assert resp.status_code == 200

    data = resp.json()
    assert data["active"] is True
    assert data["tier"] == "svip"
    assert data["tier_id"] == tiers["svip"].id
    assert data["tier_display_name"] == tiers["svip"].display_name
    assert data["expires_at"] is not None
    assert data["started_at"] is not None
    assert data["benefits"]["exclusive_scenes"] is True
    assert data["benefits"]["unlimited_replay"] is True


# ── Upgrade / expiration flows ─────────────────────────────────────


@pytest.mark.asyncio
async def test_subscribe_upgrade_tier(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """Upgrading from VIP to SVIP deactivates the old sub and starts a new one."""
    tiers = await _seed_tiers(db)
    user = await _get_auth_user(db)
    user.gem_balance = 500
    await db.commit()

    # First, subscribe to VIP.
    first = await auth_client.post(f"/api/subscription/subscribe/{tiers['vip'].id}")
    assert first.status_code == 200

    # Then, upgrade to SVIP.
    second = await auth_client.post(f"/api/subscription/subscribe/{tiers['svip'].id}")
    assert second.status_code == 200
    assert second.json()["tier"] == "svip"

    # The old VIP sub must be deactivated; the new SVIP sub must be active.
    sub_res = await db.execute(
        select(UserSubscription).where(UserSubscription.user_id == user.id)
    )
    subs = sub_res.scalars().all()
    assert len(subs) == 2
    by_tier = {s.tier_id: s for s in subs}
    assert by_tier[tiers["vip"].id].is_active is False
    assert by_tier[tiers["svip"].id].is_active is True

    # /my-subscription reflects the upgraded tier.
    status = await auth_client.get("/api/subscription/my-subscription")
    assert status.json()["tier"] == "svip"


@pytest.mark.asyncio
async def test_subscription_expiration(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """An expired UserSubscription is treated as inactive by status endpoint."""
    tiers = await _seed_tiers(db)
    user = await _get_auth_user(db)

    # Insert an already-expired subscription directly.
    expired = UserSubscription(
        user_id=user.id,
        tier_id=tiers["vip"].id,
        started_at=datetime.utcnow() - timedelta(days=60),
        expires_at=datetime.utcnow() - timedelta(days=1),
        is_active=True,  # flag still on, but date is past
        auto_renew=False,
    )
    db.add(expired)
    await db.commit()

    resp = await auth_client.get("/api/subscription/my-subscription")
    assert resp.status_code == 200
    data = resp.json()
    assert data["active"] is False
    assert data["tier"] == "free"
    assert data["tier_id"] is None


# ── Benefits surface + gem accounting ──────────────────────────────


@pytest.mark.asyncio
async def test_tier_features_match(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """The benefits dict returned for each tier mirrors the seeded JSON."""
    tiers = await _seed_tiers(db)

    resp = await auth_client.get("/api/subscription/tiers")
    assert resp.status_code == 200
    by_name = {t["tier_name"]: t for t in resp.json()}

    assert by_name["free"]["benefits"] == tiers["free"].benefits_json
    assert by_name["vip"]["benefits"] == tiers["vip"].benefits_json
    assert by_name["svip"]["benefits"] == tiers["svip"].benefits_json

    # Spot-check key flags expected by chat / content gating.
    assert by_name["vip"]["benefits"]["priority_dm"] is True
    assert by_name["svip"]["benefits"]["unlimited_replay"] is True
    # Free tier must not unlock paywalled features.
    assert "hd_images" not in by_name["free"]["benefits"]


@pytest.mark.asyncio
async def test_gem_deduction_on_subscribe(
    auth_client: AsyncClient,
    db: AsyncSession,
):
    """Subscribing debits the user's gem_balance and writes a GemTransaction."""
    tiers = await _seed_tiers(db)
    user = await _get_auth_user(db)
    user.gem_balance = 300
    await db.commit()
    starting_balance = user.gem_balance

    resp = await auth_client.post(f"/api/subscription/subscribe/{tiers['svip'].id}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["gems_charged"] == tiers["svip"].price_gems
    assert resp.json()["remaining_balance"] == starting_balance - tiers["svip"].price_gems

    # Verify persisted user balance.
    await db.refresh(user)
    assert user.gem_balance == starting_balance - tiers["svip"].price_gems

    # Verify a "subscription" GemTransaction was logged with the negative amount.
    tx_res = await db.execute(
        select(GemTransaction)
        .where(GemTransaction.user_id == user.id)
        .where(GemTransaction.tx_type == "subscription")
    )
    txs = tx_res.scalars().all()
    assert len(txs) == 1
    assert txs[0].amount == -tiers["svip"].price_gems
    assert txs[0].balance_after == user.gem_balance
