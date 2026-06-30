"""
FCM Token Endpoint Tests

Tests for ``backend/api/endpoints/fcm.py``:
- POST   /api/fcm/register   - register / upsert a device token
- DELETE /api/fcm/unregister - remove a token owned by the current user
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user_fcm_token import UserFcmToken


@pytest.mark.asyncio
async def test_register_token_success(
    auth_client: AsyncClient, db: AsyncSession
):
    """POST /api/fcm/register persists a new UserFcmToken row."""
    token = "fcm-token-success-001"

    resp = await auth_client.post(
        "/api/fcm/register",
        json={
            "token": token,
            "device_name": "Pixel 7",
            "platform": "android",
        },
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"message": "FCM token registered successfully"}

    result = await db.execute(
        select(UserFcmToken).where(UserFcmToken.token == token)
    )
    row = result.scalar_one()
    assert row.device_name == "Pixel 7"
    assert row.platform == "android"
    assert row.user_id is not None


@pytest.mark.asyncio
async def test_register_token_duplicate(
    auth_client: AsyncClient, db: AsyncSession
):
    """Registering the same token twice is idempotent — a single row remains
    and its metadata is updated to the latest payload."""
    token = "fcm-token-dup-002"

    first = await auth_client.post(
        "/api/fcm/register",
        json={"token": token, "device_name": "Old Device", "platform": "android"},
    )
    assert first.status_code == 200

    second = await auth_client.post(
        "/api/fcm/register",
        json={"token": token, "device_name": "New Device", "platform": "ios"},
    )
    assert second.status_code == 200

    rows = (
        await db.execute(select(UserFcmToken).where(UserFcmToken.token == token))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].device_name == "New Device"
    assert rows[0].platform == "ios"


@pytest.mark.asyncio
async def test_unregister_token_success(
    auth_client: AsyncClient, db: AsyncSession
):
    """DELETE /api/fcm/unregister removes the matching row from the DB."""
    token = "fcm-token-unreg-003"

    reg = await auth_client.post(
        "/api/fcm/register",
        json={"token": token, "platform": "web"},
    )
    assert reg.status_code == 200

    resp = await auth_client.request(
        "DELETE",
        "/api/fcm/unregister",
        json={"token": token},
    )
    assert resp.status_code == 200
    assert resp.json() == {"message": "FCM token unregistered successfully"}

    rows = (
        await db.execute(select(UserFcmToken).where(UserFcmToken.token == token))
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_unregister_token_not_found(
    auth_client: AsyncClient, db: AsyncSession
):
    """Unregistering a token that does not exist must succeed silently
    (DELETE is idempotent — no row, no error)."""
    resp = await auth_client.request(
        "DELETE",
        "/api/fcm/unregister",
        json={"token": "does-not-exist-token"},
    )

    assert resp.status_code == 200
    assert resp.json() == {"message": "FCM token unregistered successfully"}

    rows = (
        await db.execute(
            select(UserFcmToken).where(UserFcmToken.token == "does-not-exist-token")
        )
    ).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_fcm_requires_auth(client: AsyncClient):
    """Both register and unregister must reject unauthenticated callers."""
    register_resp = await client.post(
        "/api/fcm/register",
        json={"token": "anon-token", "platform": "android"},
    )
    assert register_resp.status_code == 401

    unregister_resp = await client.request(
        "DELETE",
        "/api/fcm/unregister",
        json={"token": "anon-token"},
    )
    assert unregister_resp.status_code == 401
