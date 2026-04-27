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

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
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
