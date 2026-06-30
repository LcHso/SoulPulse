"""
SoulPulse Admin Test Configuration

Re-uses fixtures from the parent ``tests/conftest.py`` (``db``, ``client``,
``auth_client``, ``admin_client``, ``sample_persona``, ``mock_ai_service``,
``mock_image_gen``).

Defines admin-specific helpers for inserting reference data
(``sample_user``, ``sample_post`` etc.) shared across admin test modules.
"""

from typing import AsyncGenerator

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def sample_user(db: AsyncSession):
    """Create a regular (non-admin) user for admin endpoints that operate on users."""
    from core.security import hash_password
    from models.user import User

    email = "admin_test_target_user@example.com"
    existing = await db.execute(select(User).where(User.email == email))
    user = existing.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password("Target123!"),
            nickname="TargetUser",
            gem_balance=200,
            is_admin=0,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def sample_post_pending(db: AsyncSession, sample_persona):
    """Create a pending post (status=0) attached to ``sample_persona``."""
    from models.post import Post

    post = Post(
        ai_id=sample_persona.id,
        media_url="https://example.com/pending.png",
        caption="Pending caption for review",
        like_count=0,
        status=0,
        post_type="image_only",
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@pytest_asyncio.fixture
async def sample_memory(db: AsyncSession, sample_persona, sample_user):
    """Create a MemoryEntry row referenced by admin memory tests."""
    from models.memory_entry import MemoryEntry

    entry = MemoryEntry(
        user_id=sample_user.id,
        ai_id=sample_persona.id,
        content="User likes piano music in the evening.",
        memory_type="fact",
        vector_id="vec-test-1",
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


@pytest_asyncio.fixture
async def sample_scene(db: AsyncSession, sample_persona):
    """Create a ChatScene attached to ``sample_persona``."""
    from models.chat_scene import ChatScene

    scene = ChatScene(
        persona_id=sample_persona.id,
        scene_name="雨天咖啡馆",
        scene_type="date",
        setting_description="雨夜的咖啡馆，灯光昏黄。",
        system_prompt_addon="背景：你和用户在咖啡馆避雨。",
        required_intimacy=0,
        unlock_type="free",
        unlock_cost=0,
        max_messages=20,
        is_active=True,
        sort_order=1,
    )
    db.add(scene)
    await db.commit()
    await db.refresh(scene)
    return scene


@pytest_asyncio.fixture
async def sample_outfit(db: AsyncSession, sample_persona):
    """Create an OutfitConfig attached to ``sample_persona``."""
    from models.outfit_config import OutfitConfig

    outfit = OutfitConfig(
        persona_id=sample_persona.id,
        outfit_name="日常衬衫",
        category="daily",
        visual_prompt_override="white shirt, black pants",
        unlock_condition_json={"type": "free"},
        is_default=True,
        is_active=True,
        sort_order=0,
    )
    db.add(outfit)
    await db.commit()
    await db.refresh(outfit)
    return outfit


@pytest_asyncio.fixture
async def sample_world_event(db: AsyncSession):
    """Create an active WorldEvent for listing/update tests."""
    from datetime import datetime, timezone

    from models.world_event import WorldEvent

    event = WorldEvent(
        event_type="holiday",
        title="春节",
        description="春节假期。",
        start_date=datetime(2026, 2, 17, tzinfo=timezone.utc),
        end_date=datetime(2026, 2, 24, tzinfo=timezone.utc),
        affected_persona_ids=[],
        mood_modifier_json={"pleasure": 0.2},
        is_active=True,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event
