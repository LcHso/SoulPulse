"""
Tests for notification API endpoints.

Covers:
- GET  /api/notifications              -> list with pagination, ordering, unread_count
- POST /api/notifications/{id}/read    -> mark a single notification as read
- Auth requirement for all endpoints
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from models.notification import Notification
from models.user import User


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _clean_notifications(engine):
    """Wipe notifications before each test (engine is session-scoped)."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        await s.execute(delete(Notification))
        # Also remove any extra users we created in other tests, but keep the
        # auth_client's primary user so its registration short-circuit works.
        await s.execute(
            delete(User).where(User.email != "testuser@example.com")
        )
        await s.commit()
    yield


@pytest_asyncio.fixture
async def session_factory(engine):
    """Provide an ``async_sessionmaker`` bound to the test engine.

    Tests need to open fresh sessions for verification *after* the API call
    has run – reusing the ``db`` fixture's session can hit a closed underlying
    connection on SQLite in-memory + StaticPool.
    """
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────


async def _get_auth_user_id(
    factory: async_sessionmaker, email: str = "testuser@example.com"
) -> int:
    """Fetch the id of the user created by the ``auth_client`` fixture."""
    async with factory() as s:
        result = await s.execute(select(User).where(User.email == email))
        return result.scalar_one().id


async def _create_notification(
    factory: async_sessionmaker,
    user_id: int,
    *,
    title: str = "Title",
    body: str = "Body",
    type_: str = "proactive_dm",
    is_read: int = 0,
    created_at: datetime | None = None,
) -> int:
    """Insert a Notification row in a fresh session and return its id."""
    async with factory() as s:
        notif = Notification(
            user_id=user_id,
            type=type_,
            title=title,
            body=body,
            is_read=is_read,
        )
        if created_at is not None:
            notif.created_at = created_at
        s.add(notif)
        await s.commit()
        await s.refresh(notif)
        return notif.id


async def _get_notification(factory: async_sessionmaker, notif_id: int) -> Notification | None:
    async with factory() as s:
        result = await s.execute(
            select(Notification).where(Notification.id == notif_id)
        )
        return result.scalar_one_or_none()


# ──────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_notifications_success(auth_client: AsyncClient, session_factory):
    """GET /api/notifications returns the user's notifications with metadata."""
    user_id = await _get_auth_user_id(session_factory)
    await _create_notification(session_factory, user_id, title="Hello", body="World")
    await _create_notification(session_factory, user_id, title="Hi", body="There")

    resp = await auth_client.get("/api/notifications")
    assert resp.status_code == 200

    data = resp.json()
    assert "notifications" in data
    assert "unread_count" in data
    assert "has_more" in data
    assert len(data["notifications"]) == 2
    assert data["unread_count"] == 2
    assert data["has_more"] is False

    # Schema sanity: each item carries the documented keys.
    item = data["notifications"][0]
    for key in ("id", "type", "title", "body", "is_read", "created_at"):
        assert key in item


@pytest.mark.asyncio
async def test_get_notifications_empty(auth_client: AsyncClient):
    """A user with no notifications gets an empty list and zero counts."""
    resp = await auth_client.get("/api/notifications")
    assert resp.status_code == 200

    data = resp.json()
    assert data["notifications"] == []
    assert data["unread_count"] == 0
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_get_notifications_paginated(auth_client: AsyncClient, session_factory):
    """``limit`` and ``offset`` query params slice results, and ``has_more`` flips."""
    user_id = await _get_auth_user_id(session_factory)
    base = datetime.utcnow()
    for i in range(5):
        await _create_notification(
            session_factory,
            user_id,
            title=f"Notif {i}",
            created_at=base - timedelta(minutes=i),
        )

    # First page – 2 items, more remaining.
    resp = await auth_client.get(
        "/api/notifications", params={"limit": 2, "offset": 0}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["notifications"]) == 2
    assert data["has_more"] is True

    # Last page – 1 item, no more.
    resp = await auth_client.get(
        "/api/notifications", params={"limit": 2, "offset": 4}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["notifications"]) == 1
    assert data["has_more"] is False


@pytest.mark.asyncio
async def test_mark_notification_read(auth_client: AsyncClient, session_factory):
    """POST /api/notifications/{id}/read flips ``is_read`` to 1 in the DB."""
    user_id = await _get_auth_user_id(session_factory)
    notif_id = await _create_notification(
        session_factory, user_id, title="Unread", is_read=0
    )

    resp = await auth_client.post(f"/api/notifications/{notif_id}/read")
    assert resp.status_code == 200
    assert resp.json().get("message") == "ok"

    # Re-read from DB to confirm persistence (auth_client uses a different session).
    updated = await _get_notification(session_factory, notif_id)
    assert updated is not None
    assert updated.is_read == 1


@pytest.mark.asyncio
async def test_mark_notification_not_found(auth_client: AsyncClient):
    """Marking a non-existent notification id is a safe no-op (returns 200 ok)."""
    # The endpoint does ``scalar_one_or_none`` and silently skips missing rows.
    resp = await auth_client.post("/api/notifications/999999/read")
    assert resp.status_code == 200
    assert resp.json().get("message") == "ok"


@pytest.mark.asyncio
async def test_mark_notification_wrong_user(
    auth_client: AsyncClient, session_factory
):
    """A user cannot mark another user's notification as read."""
    from core.security import hash_password

    # Insert a second user + their notification in a fresh session.
    async with session_factory() as s:
        other = User(
            email="other_user@example.com",
            hashed_password=hash_password("OtherPass123!"),
            nickname="Other",
        )
        s.add(other)
        await s.commit()
        await s.refresh(other)
        other_id = other.id

    notif_id = await _create_notification(
        session_factory, other_id, title="Not yours", is_read=0
    )

    # The endpoint filters by ``user_id == current_user.id`` so this is a no-op.
    resp = await auth_client.post(f"/api/notifications/{notif_id}/read")
    assert resp.status_code == 200

    untouched = await _get_notification(session_factory, notif_id)
    assert untouched is not None
    assert untouched.is_read == 0  # still unread – ownership check held.


@pytest.mark.asyncio
async def test_notifications_ordered_by_date(
    auth_client: AsyncClient, session_factory
):
    """Most recently created notifications appear first."""
    user_id = await _get_auth_user_id(session_factory)
    now = datetime.utcnow()

    await _create_notification(
        session_factory, user_id, title="Old", created_at=now - timedelta(days=2)
    )
    await _create_notification(
        session_factory, user_id, title="Newest", created_at=now
    )
    await _create_notification(
        session_factory, user_id, title="Middle", created_at=now - timedelta(days=1)
    )

    resp = await auth_client.get("/api/notifications")
    assert resp.status_code == 200
    titles = [n["title"] for n in resp.json()["notifications"]]
    assert titles == ["Newest", "Middle", "Old"]


@pytest.mark.asyncio
async def test_notifications_require_auth(client: AsyncClient):
    """All notification endpoints reject unauthenticated requests with 401."""
    resp = await client.get("/api/notifications")
    assert resp.status_code == 401

    resp = await client.post("/api/notifications/1/read")
    assert resp.status_code == 401
