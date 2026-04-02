"""
认证端点模块

================================================================================
功能概述
================================================================================
本模块提供用户认证相关的 REST API 端点：
- 用户注册：创建新用户账户
- 用户登录：验证凭据并返回 JWT 令牌
- 获取当前用户：返回已认证用户信息
- 更新个人资料：修改昵称、头像等
- 修改密码：更新用户密码
- 删除账户：永久删除用户账户

================================================================================
设计理念
================================================================================
1. JWT 令牌认证：使用 JSON Web Token 进行无状态认证
2. OAuth2 兼容：登录接口兼容 OAuth2 密码模式
3. 安全密码存储：使用 bcrypt 哈希存储密码
4. 输入验证：使用 Pydantic 模型验证请求和响应

================================================================================
API 端点列表
================================================================================
POST   /api/auth/register  - 注册新用户
POST   /api/auth/login     - 登录获取令牌
GET    /api/auth/me        - 获取当前用户信息
PATCH  /api/auth/profile   - 更新个人资料
PATCH  /api/auth/password  - 修改密码
DELETE /api/auth/account   - 删除账户
"""

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


# ── Pydantic 数据模型（请求/响应 Schema）──────────

class RegisterRequest(BaseModel):
    """
    用户注册请求模型。

    Attributes:
        email: 用户邮箱（必填）
        password: 用户密码（必填）
        nickname: 用户昵称（默认 "User"）
        gender: 性别（默认 "not_specified"）
        orientation_preference: 偏好性别（默认 "male"）
    """
    email: str
    password: str
    nickname: str = "User"
    gender: str = "not_specified"
    orientation_preference: str = "male"


class TokenResponse(BaseModel):
    """
    JWT 令牌响应模型。

    Attributes:
        access_token: 访问令牌
        token_type: 令牌类型（固定为 "bearer"）
    """
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    """
    用户信息输出模型。

    Attributes:
        id: 用户 ID
        email: 用户邮箱
        nickname: 用户昵称
        avatar_url: 头像 URL（可选）
        gender: 性别
        orientation_preference: 偏好性别
        gem_balance: 宝石余额
        is_admin: 是否为管理员
    """
    id: int
    email: str
    nickname: str
    avatar_url: Optional[str] = None
    gender: str = "not_specified"
    orientation_preference: str = "male"
    gem_balance: int
    is_admin: int = 0


class ProfileUpdateRequest(BaseModel):
    """
    个人资料更新请求模型。

    Attributes:
        nickname: 新昵称（可选）
        avatar_url: 新头像 URL（可选）
        gender: 性别（可选）
        orientation_preference: 偏好性别（可选）
    """
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    gender: Optional[str] = None
    orientation_preference: Optional[str] = None


class PasswordChangeRequest(BaseModel):
    """
    密码修改请求模型。

    Attributes:
        current_password: 当前密码
        new_password: 新密码
    """
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    """
    删除账户请求模型。

    Attributes:
        password: 用户密码（用于确认身份）
    """
    password: str


# ── API 端点定义 ────────────────────────────────────────

@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """
    注册新用户。

    创建新用户账户。如果邮箱已被注册，返回 400 错误。

    Args:
        body: 注册请求体
        db: 异步数据库会话

    Returns:
        UserOut: 新创建的用户信息

    Raises:
        HTTPException: 邮箱已被注册时返回 400 错误
    """
    # 检查邮箱是否已被注册
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # 创建新用户
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
        is_admin=user.is_admin,
    )


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    """
    用户登录，返回 JWT 令牌。

    使用 OAuth2 密码模式进行认证。验证邮箱和密码，
    如果正确则返回访问令牌。

    Args:
        form: OAuth2 密码模式表单（username 为邮箱，password 为密码）
        db: 异步数据库会话

    Returns:
        TokenResponse: JWT 访问令牌

    Raises:
        HTTPException: 邮箱或密码错误时返回 401 错误
    """
    # 查找用户
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    # 验证用户存在且密码正确
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # 生成 JWT 令牌
    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def me(current_user: User = Depends(get_current_user)):
    """
    获取当前已认证用户信息。

    需要在请求头中携带有效的 JWT 令牌。

    Args:
        current_user: 当前已认证用户（通过依赖注入获取）

    Returns:
        UserOut: 当前用户信息
    """
    return UserOut(
        id=current_user.id,
        email=current_user.email,
        nickname=current_user.nickname,
        avatar_url=current_user.avatar_url,
        gender=current_user.gender,
        orientation_preference=current_user.orientation_preference,
        gem_balance=current_user.gem_balance,
        is_admin=current_user.is_admin,
    )


@router.patch("/profile", response_model=UserOut)
async def update_profile(
    body: ProfileUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    更新用户个人资料。

    允许修改昵称、头像、性别和偏好性别。

    Args:
        body: 个人资料更新请求体
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        UserOut: 更新后的用户信息

    Raises:
        HTTPException: 性别或偏好值无效时返回 400 错误
    """
    # 更新昵称（限制长度为 100 字符）
    if body.nickname is not None:
        current_user.nickname = body.nickname.strip()[:100]
    # 更新头像
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url
    # 更新性别（必须是有效值）
    if body.gender is not None:
        if body.gender not in ("male", "female", "non_binary", "not_specified"):
            raise HTTPException(status_code=400, detail="Invalid gender value")
        current_user.gender = body.gender
    # 更新偏好性别（必须是有效值）
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
        is_admin=current_user.is_admin,
    )


@router.patch("/password")
async def change_password(
    body: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    修改用户密码。

    需要提供当前密码进行验证。新密码长度不能少于 6 个字符。

    Args:
        body: 密码修改请求体
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 成功消息

    Raises:
        HTTPException: 当前密码错误或新密码太短时返回 400 错误
    """
    # 验证当前密码
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    # 验证新密码长度
    if len(body.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # 更新密码
    current_user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return {"message": "Password updated successfully"}


@router.delete("/account")
async def delete_account(
    body: DeleteAccountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    永久删除用户账户。

    需要提供密码进行身份确认。此操作不可逆。

    Args:
        body: 删除账户请求体
        db: 异步数据库会话
        current_user: 当前已认证用户

    Returns:
        dict: 成功消息

    Raises:
        HTTPException: 密码错误时返回 400 错误
    """
    # 验证密码
    if not verify_password(body.password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is incorrect")

    # 删除用户
    await db.delete(current_user)
    await db.commit()
    return {"message": "Account deleted successfully"}