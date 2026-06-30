"""
SoulPulse Test Configuration

Provides pytest fixtures for:
- Test database (in-memory SQLite)
- Async HTTP client
- Authentication helpers
"""

import asyncio
import os
import sys
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import Base, get_db
from main import app

# Import all models to ensure tables are created
# This mirrors the imports in core/database.py init_db()
import models.user  # noqa: F401
import models.ai_persona  # noqa: F401
import models.post  # noqa: F401
import models.story  # noqa: F401
import models.comment  # noqa: F401
import models.chat_message  # noqa: F401
import models.interaction  # noqa: F401
import models.emotion_state  # noqa: F401
import models.memory_entry  # noqa: F401
import models.notification  # noqa: F401
import models.follow  # noqa: F401
import models.user_like  # noqa: F401
import models.saved_post  # noqa: F401
import models.proactive_dm  # noqa: F401
import models.relational_anchor  # noqa: F401
import models.emotion_trigger_log  # noqa: F401
import models.chat_summary  # noqa: F401
import models.story_view  # noqa: F401
# SDC admin models
import models.admin_audit_log  # noqa: F401
import models.api_usage_log  # noqa: F401
import models.system_config  # noqa: F401
import models.content_moderation_log  # noqa: F401
import models.global_knowledge_entry  # noqa: F401
import models.visual_dna_version  # noqa: F401
import models.gacha_script  # noqa: F401
import models.virtual_gift  # noqa: F401
import models.gem_transaction  # noqa: F401
import models.milestone_config  # noqa: F401
# Models required by admin tests
import models.character_launch  # noqa: F401
import models.world_event  # noqa: F401
import models.chat_scene  # noqa: F401
import models.outfit_config  # noqa: F401
import models.character_arc  # noqa: F401
import models.subscription  # noqa: F401
import models.asset_registry  # noqa: F401

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create async engine with in-memory SQLite database."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide an async database session for each test."""
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(engine) -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client with database override."""
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async def override_get_db():
        async with session_factory() as session:
            yield session
    
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient) -> AsyncClient:
    """
    Provide an authenticated client with a registered user.
    
    Registers a test user and logs in, then attaches the token to the client.
    """
    # Register a test user
    register_resp = await client.post("/api/auth/register", json={
        "email": "testuser@example.com",
        "password": "TestPass123!",
        "nickname": "TestUser"
    })
    
    # Login to get token (OAuth2PasswordRequestForm requires form data)
    login_resp = await client.post(
        "/api/auth/login",
        data={
            "username": "testuser@example.com",
            "password": "TestPass123!"
        }
    )
    
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token_data = login_resp.json()
    token = token_data.get("access_token")
    
    # Attach authorization header
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    
    # Clean up
    if "Authorization" in client.headers:
        del client.headers["Authorization"]


@pytest_asyncio.fixture
async def test_user_token(client: AsyncClient) -> str:
    """
    Register a test user and return its access token.
    """
    # Register user
    await client.post("/api/auth/register", json={
        "email": "tokentest@example.com",
        "password": "TestPass123!",
        "nickname": "TokenUser"
    })
    
    # Login to get token
    login_resp = await client.post(
        "/api/auth/login",
        data={
            "username": "tokentest@example.com",
            "password": "TestPass123!"
        }
    )
    
    token_data = login_resp.json()
    return token_data.get("access_token")


# ──────────────────────────────────────────────────────────────────────
# Extended fixtures: admin client, sample data, service mocks
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an authenticated client whose user has ``is_admin=1``.

    Creates the admin user directly in the DB (bypassing the public register
    endpoint, which does not expose ``is_admin``), then mints a JWT via
    ``create_access_token`` and attaches it to the client headers.
    """
    from core.security import create_access_token, hash_password
    from models.user import User

    admin_email = "admin_fixture@example.com"

    # Reuse if a previous fixture in the same session already created it
    existing = await db.execute(select(User).where(User.email == admin_email))
    admin = existing.scalar_one_or_none()
    if admin is None:
        admin = User(
            email=admin_email,
            hashed_password=hash_password("AdminPass123!"),
            nickname="AdminUser",
            is_admin=1,
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

    token = create_access_token({"sub": str(admin.id)})
    client.headers["Authorization"] = f"Bearer {token}"
    try:
        yield client
    finally:
        if "Authorization" in client.headers:
            del client.headers["Authorization"]


@pytest_asyncio.fixture
async def sample_persona(db: AsyncSession):
    """Create a realistic AIPersona row for tests and return the ORM object."""
    from models.ai_persona import AIPersona

    persona = AIPersona(
        name="陆晨曦",
        bio="温柔的钢琴家，擅长聆听他人的故事。",
        profession="钢琴家",
        personality_prompt=(
            "你是陆晨曦，一位温柔细腻的青年钢琴家。说话轻柔，富有同理心，"
            "喜欢用音乐和文字安慰他人。"
        ),
        gender_tag="male",
        category="otome",
        archetype="温柔治愈",
        avatar_url="https://example.com/avatars/luchenxi.png",
        is_active=1,
        sort_order=1,
    )
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


@pytest_asyncio.fixture
async def sample_posts(db: AsyncSession, sample_persona):
    """Create three Post rows linked to ``sample_persona`` and return them."""
    from models.post import Post

    posts = [
        Post(
            ai_id=sample_persona.id,
            media_url=f"https://example.com/posts/{i}.png",
            caption=f"Sample post {i} caption",
            like_count=10 * i,
            is_close_friend=(i == 3),
            status=1,  # published
            post_type="image_only",
        )
        for i in range(1, 4)
    ]
    db.add_all(posts)
    await db.commit()
    for p in posts:
        await db.refresh(p)
    return posts


@pytest_asyncio.fixture
async def sample_interaction(db: AsyncSession, sample_persona):
    """Create an Interaction record with non-zero intimacy and return it.

    A test User is created on the fly so the FK constraint to ``users`` holds.
    """
    from core.security import hash_password
    from models.interaction import Interaction
    from models.user import User

    interaction_email = "interaction_user@example.com"
    existing = await db.execute(select(User).where(User.email == interaction_email))
    user = existing.scalar_one_or_none()
    if user is None:
        user = User(
            email=interaction_email,
            hashed_password=hash_password("TestPass123!"),
            nickname="InteractionUser",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    interaction = Interaction(
        user_id=user.id,
        ai_id=sample_persona.id,
        intimacy_score=42.0,
        last_chat_summary="用户和陆晨曦聊了最近压力很大的工作。",
        streak_count=3,
        total_interaction_days=5,
    )
    db.add(interaction)
    await db.commit()
    await db.refresh(interaction)
    return interaction


@pytest.fixture
def mock_ai_service(monkeypatch):
    """Patch ``aliyun_ai_service.chat_with_ai`` to return a fixed reply.

    Returns the AsyncMock so tests can assert on call args / change return
    value (e.g. ``mock_ai_service.return_value = "..."``).
    """
    from services import aliyun_ai_service

    fake_reply = AsyncMock(return_value="这是一条来自 mock AI 的固定回复。")
    monkeypatch.setattr(aliyun_ai_service, "chat_with_ai", fake_reply)
    return fake_reply


@pytest.fixture
def mock_vector_store(monkeypatch):
    """Patch ChromaDB-backed vector store helpers with no-op stubs.

    Returns a ``MagicMock`` namespace whose attributes mirror the patched
    callables (``add_memory``, ``query_memories``, ``add_anchor``,
    ``query_anchors``).
    """
    from services import vector_store

    ns = MagicMock()
    ns.add_memory = MagicMock(return_value=None)
    ns.query_memories = MagicMock(return_value=[])
    ns.add_anchor = MagicMock(return_value=None)
    ns.query_anchors = MagicMock(return_value=[])

    monkeypatch.setattr(vector_store, "add_memory", ns.add_memory)
    monkeypatch.setattr(vector_store, "query_memories", ns.query_memories)
    monkeypatch.setattr(vector_store, "add_anchor", ns.add_anchor)
    monkeypatch.setattr(vector_store, "query_anchors", ns.query_anchors)

    # Also expose conventional alias names referenced by some callers/tests.
    monkeypatch.setattr(vector_store, "add_memories", ns.add_memory, raising=False)
    monkeypatch.setattr(vector_store, "search", ns.query_memories, raising=False)

    return ns


@pytest.fixture
def mock_image_gen(monkeypatch):
    """Patch ``image_gen_service`` image generators to return a fake URL."""
    from services import image_gen_service

    fake_url = "https://example.com/fake-generated-image.png"
    fake_post = AsyncMock(return_value=fake_url)
    fake_image = AsyncMock(return_value=[fake_url])

    monkeypatch.setattr(
        image_gen_service, "generate_post_image_unified", fake_post
    )
    # Common alias used in some callers/tests.
    monkeypatch.setattr(
        image_gen_service, "generate_post_image", fake_post, raising=False
    )
    monkeypatch.setattr(
        image_gen_service, "generate_image", fake_image, raising=False
    )
    return fake_post
