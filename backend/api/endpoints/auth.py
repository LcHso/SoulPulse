from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from core.database import get_db
from core.security import hash_password, verify_password, create_access_token, get_current_user
from models.user import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------- Schemas ----------

class RegisterRequest(BaseModel):
    email: str
    password: str
    nickname: str = "User"
    gender: str = "not_specified"
    orientation_preference: str = "male"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    nickname: str
    avatar_url: Optional[str] = None
    gender: str = "not_specified"
    orientation_preference: str = "male"
    gem_balance: int


class ProfileUpdateRequest(BaseModel):
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    gender: Optional[str] = None
    orientation_preference: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    password: str


# ---------- Endpoints ----------

@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        nickname=body.nickname,
        gender=body.gender,
        orientation_preference=body.orientation_preference,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return UserOut(
        id=user.id, email=user.email, nickname=user.nickname,
        avatar_url=user.avatar_url, gender=user.gender,
        orientation_preference=user.orientation_preference,
        gem_balance=user.gem_balance,
    )


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """Login with email and password, returns JWT."""
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info."""
    return UserOut(
        id=current_user.id,
        email=current_user.email,
        nickname=current_user.nickname,
        avatar_url=current_user.avatar_url,
        gender=current_user.gender,
        orientation_preference=current_user.orientation_preference,
        gem_balance=current_user.gem_balance,
    )


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    body: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user profile fields."""
    if body.nickname is not None:
        current_user.nickname = body.nickname.strip()[:100]
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    if body.gender is not None:
        if body.gender not in ("male", "female", "non_binary", "not_specified"):
            raise HTTPException(status_code=400, detail="Invalid gender value")
        current_user.gender = body.gender
    if body.orientation_preference is not None:
        if body.orientation_preference not in ("male", "female", "both", "other"):
            raise HTTPException(status_code=400, detail="Invalid orientation value")
        current_user.orientation_preference = body.orientation_preference

    await db.commit()
    await db.refresh(current_user)
    return UserOut(
        id=current_user.id, email=current_user.email,
        nickname=current_user.nickname, avatar_url=current_user.avatar_url,
        gender=current_user.gender,
        orientation_preference=current_user.orientation_preference,
        gem_balance=current_user.gem_balance,
    )


@router.patch("/password")
async def change_password(
    body: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change user password."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    current_user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return {"message": "Password updated successfully"}


@router.delete("/account")
async def delete_account(
    body: DeleteAccountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete user account permanently."""
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect")

    await db.delete(current_user)
    await db.commit()
    return {"message": "Account deleted successfully"}
