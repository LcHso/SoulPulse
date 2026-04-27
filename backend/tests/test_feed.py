"""
Feed Endpoint Tests

Tests for:
- Feed posts retrieval
- Like/Unlike operations (idempotency)
- Save/Unsave operations
- Feed pagination
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.ai_persona import AIPersona
from models.post import Post


async def create_test_posts(db: AsyncSession) -> dict:
    """Create test AI persona and posts in the database."""
    # Create AI persona
    persona = AIPersona(
        name="Test AI",
        bio="A test AI persona",
        profession="Test Subject",
        personality_prompt="You are a helpful test assistant.",
        gender_tag="male",
        category="general",
        avatar_url="https://example.com/avatar.png",
    )
    db.add(persona)
    await db.flush()
    
    # Create posts
    posts = []
    for i in range(5):
        post = Post(
            ai_id=persona.id,
            media_url=f"https://example.com/post_{i}.png",
            caption=f"Test post {i}",
            like_count=0,
            is_close_friend=(i == 4),  # Last post is close friends only
        )
        db.add(post)
        posts.append(post)
    
    await db.commit()
    
    # Refresh to get IDs
    for post in posts:
        await db.refresh(post)
    await db.refresh(persona)
    
    return {"persona": persona, "posts": posts}


class TestFeedPosts:
    """Tests for feed posts retrieval."""

    @pytest.mark.asyncio
    async def test_get_posts_empty(self, auth_client: AsyncClient):
        """Test getting posts when none exist."""
        resp = await auth_client.get("/api/feed/posts")
        
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_posts_with_data(self, auth_client: AsyncClient, db: AsyncSession):
        """Test getting posts returns list of posts."""
        # Create test data
        data = await create_test_posts(db)
        
        resp = await auth_client.get("/api/feed/posts")
        
        assert resp.status_code == 200
        result = resp.json()
        # Close friend posts require intimacy >= 6, so only 4 posts visible
        assert len(result) == 4
        assert result[0]["caption"].startswith("Test post")

    @pytest.mark.asyncio
    async def test_get_posts_pagination(self, auth_client: AsyncClient, db: AsyncSession):
        """Test feed pagination with limit and offset."""
        # Create test data
        await create_test_posts(db)
        
        # Get first 2 posts
        resp = await auth_client.get("/api/feed/posts?limit=2&offset=0")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        
        # Get next 2 posts
        resp = await auth_client.get("/api/feed/posts?limit=2&offset=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_get_posts_requires_auth(self, client: AsyncClient):
        """Test that feed endpoint requires authentication."""
        resp = await client.get("/api/feed/posts")
        
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_single_post(self, auth_client: AsyncClient, db: AsyncSession):
        """Test getting a single post by ID."""
        data = await create_test_posts(db)
        post_id = data["posts"][0].id
        
        resp = await auth_client.get(f"/api/feed/posts/{post_id}")
        
        assert resp.status_code == 200
        assert resp.json()["id"] == post_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_post(self, auth_client: AsyncClient):
        """Test getting a non-existent post returns 404."""
        resp = await auth_client.get("/api/feed/posts/99999")
        
        assert resp.status_code == 404


class TestLikePost:
    """Tests for post like operations."""

    @pytest.mark.asyncio
    async def test_like_post_success(self, auth_client: AsyncClient, db: AsyncSession):
        """Test successfully liking a post."""
        data = await create_test_posts(db)
        post_id = data["posts"][0].id
        
        resp = await auth_client.post(f"/api/feed/posts/{post_id}/like")
        
        assert resp.status_code == 200
        result = resp.json()
        assert result["status"] == "liked"
        assert result["like_count"] == 1

    @pytest.mark.asyncio
    async def test_like_post_idempotent(self, auth_client: AsyncClient, db: AsyncSession):
        """Test that liking twice is idempotent."""
        data = await create_test_posts(db)
        post_id = data["posts"][1].id
        
        # First like
        resp1 = await auth_client.post(f"/api/feed/posts/{post_id}/like")
        assert resp1.json()["status"] == "liked"
        
        # Second like (should be idempotent)
        resp2 = await auth_client.post(f"/api/feed/posts/{post_id}/like")
        assert resp2.json()["status"] == "already_liked"
        
        # Like count should still be 1
        assert resp2.json()["like_count"] == 1

    @pytest.mark.asyncio
    async def test_like_nonexistent_post(self, auth_client: AsyncClient):
        """Test liking a non-existent post returns 404."""
        resp = await auth_client.post("/api/feed/posts/99999/like")
        
        assert resp.status_code == 404


class TestUnlikePost:
    """Tests for post unlike operations."""

    @pytest.mark.asyncio
    async def test_unlike_post_success(self, auth_client: AsyncClient, db: AsyncSession):
        """Test successfully unliking a post."""
        data = await create_test_posts(db)
        post_id = data["posts"][0].id
        
        # First like the post
        await auth_client.post(f"/api/feed/posts/{post_id}/like")
        
        # Then unlike
        resp = await auth_client.delete(f"/api/feed/posts/{post_id}/like")
        
        assert resp.status_code == 200
        assert resp.json()["status"] == "unliked"
        assert resp.json()["like_count"] == 0

    @pytest.mark.asyncio
    async def test_unlike_post_idempotent(self, auth_client: AsyncClient, db: AsyncSession):
        """Test that unliking without prior like is idempotent."""
        data = await create_test_posts(db)
        post_id = data["posts"][2].id
        
        # Unlike without prior like
        resp = await auth_client.delete(f"/api/feed/posts/{post_id}/like")
        
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_liked"

    @pytest.mark.asyncio
    async def test_unlike_nonexistent_post(self, auth_client: AsyncClient):
        """Test unliking a non-existent post returns 404."""
        resp = await auth_client.delete("/api/feed/posts/99999/like")
        
        assert resp.status_code == 404


class TestSavePost:
    """Tests for post save operations."""

    @pytest.mark.asyncio
    async def test_save_post_success(self, auth_client: AsyncClient, db: AsyncSession):
        """Test successfully saving a post."""
        data = await create_test_posts(db)
        post_id = data["posts"][0].id
        
        resp = await auth_client.post(f"/api/feed/posts/{post_id}/save")
        
        assert resp.status_code == 200
        assert resp.json()["saved"] == True

    @pytest.mark.asyncio
    async def test_save_post_idempotent(self, auth_client: AsyncClient, db: AsyncSession):
        """Test that saving twice is idempotent."""
        data = await create_test_posts(db)
        post_id = data["posts"][1].id
        
        # First save
        resp1 = await auth_client.post(f"/api/feed/posts/{post_id}/save")
        assert resp1.json()["saved"] == True
        
        # Second save (should still return True)
        resp2 = await auth_client.post(f"/api/feed/posts/{post_id}/save")
        assert resp2.json()["saved"] == True

    @pytest.mark.asyncio
    async def test_save_nonexistent_post(self, auth_client: AsyncClient):
        """Test saving a non-existent post returns 404."""
        resp = await auth_client.post("/api/feed/posts/99999/save")
        
        assert resp.status_code == 404


class TestUnsavePost:
    """Tests for post unsave operations."""

    @pytest.mark.asyncio
    async def test_unsave_post_success(self, auth_client: AsyncClient, db: AsyncSession):
        """Test successfully unsaving a post."""
        data = await create_test_posts(db)
        post_id = data["posts"][0].id
        
        # First save
        await auth_client.post(f"/api/feed/posts/{post_id}/save")
        
        # Then unsave
        resp = await auth_client.delete(f"/api/feed/posts/{post_id}/save")
        
        assert resp.status_code == 200
        assert resp.json()["saved"] == False

    @pytest.mark.asyncio
    async def test_unsave_post_idempotent(self, auth_client: AsyncClient, db: AsyncSession):
        """Test that unsaving without prior save is idempotent."""
        data = await create_test_posts(db)
        post_id = data["posts"][2].id
        
        # Unsave without prior save
        resp = await auth_client.delete(f"/api/feed/posts/{post_id}/save")
        
        assert resp.status_code == 200
        assert resp.json()["saved"] == False


class TestSavedPosts:
    """Tests for saved posts retrieval."""

    @pytest.mark.asyncio
    async def test_get_saved_posts_empty(self, client: AsyncClient):
        """Test getting saved posts when none saved."""
        # Register a fresh user for this test
        await client.post("/api/auth/register", json={
            "email": "savedempty@test.com",
            "password": "TestPass123!",
            "nickname": "SavedEmptyUser"
        })
        login_resp = await client.post(
            "/api/auth/login",
            data={"username": "savedempty@test.com", "password": "TestPass123!"}
        )
        token = login_resp.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        
        resp = await client.get("/api/feed/saved")
        
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_saved_posts_with_data(self, client: AsyncClient, db: AsyncSession):
        """Test getting saved posts returns saved posts."""
        # Register a fresh user for this test
        await client.post("/api/auth/register", json={
            "email": "saveddata@test.com",
            "password": "TestPass123!",
            "nickname": "SavedDataUser"
        })
        login_resp = await client.post(
            "/api/auth/login",
            data={"username": "saveddata@test.com", "password": "TestPass123!"}
        )
        token = login_resp.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        
        data = await create_test_posts(db)
        posts = data["posts"]
        
        # Save a post
        await client.post(f"/api/feed/posts/{posts[0].id}/save")
        
        # Get saved posts
        resp = await client.get("/api/feed/saved")
        
        assert resp.status_code == 200
        result = resp.json()
        assert len(result) == 1
        assert result[0]["id"] == posts[0].id
        assert result[0]["is_saved"] == True
