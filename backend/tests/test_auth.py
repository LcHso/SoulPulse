"""
Authentication Endpoint Tests

Tests for:
- User registration
- User login
- Protected endpoint access
- Duplicate email handling
- Invalid credentials handling
"""

import pytest
from httpx import AsyncClient


class TestRegister:
    """Tests for user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_new_user(self, client: AsyncClient):
        """Test successful user registration."""
        resp = await client.post("/api/auth/register", json={
            "email": "newuser@test.com",
            "password": "SecurePass123!",
            "nickname": "NewUser"
        })
        
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "newuser@test.com"
        assert data["nickname"] == "NewUser"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient):
        """Test that duplicate email registration returns error."""
        # First registration
        await client.post("/api/auth/register", json={
            "email": "dupe@test.com",
            "password": "Pass123!",
            "nickname": "User1"
        })
        
        # Second registration with same email
        resp = await client.post("/api/auth/register", json={
            "email": "dupe@test.com",
            "password": "Pass456!",
            "nickname": "User2"
        })
        
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_default_nickname(self, client: AsyncClient):
        """Test that nickname defaults to 'User' when not provided."""
        resp = await client.post("/api/auth/register", json={
            "email": "nonick@test.com",
            "password": "Pass123!"
        })
        
        assert resp.status_code == 201
        assert resp.json()["nickname"] == "User"


class TestLogin:
    """Tests for user login endpoint."""

    @pytest.mark.asyncio
    async def test_login_valid_credentials(self, client: AsyncClient):
        """Test successful login with valid credentials."""
        # Register user first
        await client.post("/api/auth/register", json={
            "email": "login@test.com",
            "password": "Pass123!",
            "nickname": "LoginUser"
        })
        
        # Login with form data (OAuth2PasswordRequestForm)
        resp = await client.post(
            "/api/auth/login",
            data={
                "username": "login@test.com",
                "password": "Pass123!"
            }
        )
        
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient):
        """Test login with wrong password returns 401."""
        # Register user
        await client.post("/api/auth/register", json={
            "email": "wrongpass@test.com",
            "password": "CorrectPass!",
            "nickname": "WrongPassUser"
        })
        
        # Login with wrong password
        resp = await client.post(
            "/api/auth/login",
            data={
                "username": "wrongpass@test.com",
                "password": "WrongPass!"
            }
        )
        
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient):
        """Test login with non-existent email returns 401."""
        resp = await client.post(
            "/api/auth/login",
            data={
                "username": "nonexistent@test.com",
                "password": "AnyPass!"
            }
        )
        
        assert resp.status_code == 401


class TestProtectedEndpoints:
    """Tests for authentication-required endpoints."""

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, auth_client: AsyncClient):
        """Test /me endpoint with valid authentication."""
        resp = await auth_client.get("/api/auth/me")
        
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "testuser@example.com"
        assert data["nickname"] == "TestUser"

    @pytest.mark.asyncio
    async def test_get_me_without_token(self, client: AsyncClient):
        """Test /me endpoint without token returns 401."""
        resp = await client.get("/api/auth/me")
        
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_with_invalid_token(self, client: AsyncClient):
        """Test /me endpoint with invalid token returns 401."""
        client.headers["Authorization"] = "Bearer invalid_token"
        resp = await client.get("/api/auth/me")
        
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_feed_requires_auth(self, client: AsyncClient):
        """Test that feed endpoint requires authentication."""
        resp = await client.get("/api/feed/posts")
        
        assert resp.status_code == 401


class TestProfileUpdate:
    """Tests for profile update endpoint."""

    @pytest.mark.asyncio
    async def test_update_nickname(self, auth_client: AsyncClient):
        """Test updating user nickname."""
        resp = await auth_client.patch("/api/auth/profile", json={
            "nickname": "NewNickname"
        })
        
        assert resp.status_code == 200
        assert resp.json()["nickname"] == "NewNickname"

    @pytest.mark.asyncio
    async def test_update_gender_valid(self, auth_client: AsyncClient):
        """Test updating gender with valid values."""
        for gender in ["male", "female", "non_binary", "not_specified"]:
            resp = await auth_client.patch("/api/auth/profile", json={
                "gender": gender
            })
            assert resp.status_code == 200
            assert resp.json()["gender"] == gender

    @pytest.mark.asyncio
    async def test_update_gender_invalid(self, auth_client: AsyncClient):
        """Test updating gender with invalid value returns 400."""
        resp = await auth_client.patch("/api/auth/profile", json={
            "gender": "invalid_gender"
        })
        
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_orientation_valid(self, auth_client: AsyncClient):
        """Test updating orientation with valid values."""
        for orientation in ["male", "female", "both", "other"]:
            resp = await auth_client.patch("/api/auth/profile", json={
                "orientation_preference": orientation
            })
            assert resp.status_code == 200
            assert resp.json()["orientation_preference"] == orientation

    @pytest.mark.asyncio
    async def test_update_orientation_invalid(self, auth_client: AsyncClient):
        """Test updating orientation with invalid value returns 400."""
        resp = await auth_client.patch("/api/auth/profile", json={
            "orientation_preference": "invalid"
        })
        
        assert resp.status_code == 400


class TestPasswordChange:
    """Tests for password change endpoint."""

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self, auth_client: AsyncClient):
        """Test password change with wrong current password."""
        resp = await auth_client.patch("/api/auth/password", json={
            "current_password": "WrongCurrentPass!",
            "new_password": "NewPass456!"
        })
        
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_change_password_too_short(self, auth_client: AsyncClient):
        """Test password change with too short new password."""
        resp = await auth_client.patch("/api/auth/password", json={
            "current_password": "TestPass123!",
            "new_password": "short"
        })
        
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_change_password_success(self, client: AsyncClient):
        """Test successful password change with new user."""
        # Register a new user for this test
        await client.post("/api/auth/register", json={
            "email": "pwdchange@test.com",
            "password": "OldPass123!",
            "nickname": "PwdUser"
        })
        
        # Login to get token
        login_resp = await client.post(
            "/api/auth/login",
            data={
                "username": "pwdchange@test.com",
                "password": "OldPass123!"
            }
        )
        token = login_resp.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"
        
        # Change password
        resp = await client.patch("/api/auth/password", json={
            "current_password": "OldPass123!",
            "new_password": "NewPass456!"
        })
        
        assert resp.status_code == 200
        
        # Verify can login with new password
        login_resp = await client.post(
            "/api/auth/login",
            data={
                "username": "pwdchange@test.com",
                "password": "NewPass456!"
            }
        )
        assert login_resp.status_code == 200
