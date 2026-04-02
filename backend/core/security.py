"""
SoulPulse 安全认证模块

本模块负责用户认证和授权，包括：
1. 密码哈希与验证
2. JWT 令牌生成与解析
3. 用户身份验证依赖注入
4. WebSocket 认证
5. 管理员权限验证

技术栈：
- passlib + bcrypt: 密码哈希
- python-jose: JWT 令牌处理
- FastAPI OAuth2: 认证流程

使用方式：
    # 在路由中使用依赖注入
    @router.get("/me")
    async def get_me(user: User = Depends(get_current_user)):
        return user

    # 管理员专属接口
    @router.get("/admin/users")
    async def list_users(admin: User = Depends(get_current_admin_user)):
        ...
"""

from datetime import datetime, timedelta, timezone
from typing import Optional, TYPE_CHECKING

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.config import settings
from core.database import get_db

if TYPE_CHECKING:
    from models.user import User

# ── 密码哈希配置 ──────────────────────────────────────────
# 使用 bcrypt 算法进行密码哈希，安全性高且自动加盐
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── OAuth2 密码模式配置 ──────────────────────────────────────────
# 指定登录接口的 URL，用于 Swagger UI 认证
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    """
    对密码进行哈希处理

    使用 bcrypt 算法对明文密码进行加密，生成安全的哈希值存储到数据库。

    Args:
        password: 明文密码

    Returns:
        str: 哈希后的密码字符串

    示例:
        hashed = hash_password("user_password_123")
    """
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """
    验证密码是否正确

    将明文密码与存储的哈希值进行比对。

    Args:
        plain: 用户输入的明文密码
        hashed: 数据库中存储的哈希值

    Returns:
        bool: 密码正确返回 True，否则返回 False

    示例:
        if verify_password(user_input, user.hashed_password):
            # 登录成功
    """
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    """
    创建 JWT 访问令牌

    根据用户数据生成 JWT 令牌，用于后续请求的身份验证。
    令牌包含过期时间，由 settings.ACCESS_TOKEN_EXPIRE_MINUTES 控制。

    Args:
        data: 要编码到令牌中的数据，通常包含用户 ID
              {"sub": user_id}

    Returns:
        str: JWT 令牌字符串

    示例:
        token = create_access_token({"sub": str(user.id)})
    """
    to_encode = data.copy()
    # 设置过期时间
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    # 使用密钥和算法编码令牌
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    """
    获取当前登录用户的依赖注入函数

    从请求头的 Authorization 字段提取并验证 JWT 令牌，
    然后返回对应的用户对象。

    用于 FastAPI 路由的依赖注入：
        @router.get("/profile")
        async def get_profile(user: User = Depends(get_current_user)):
            return user

    Args:
        token: OAuth2 方案自动提取的 JWT 令牌
        db: 数据库会话

    Returns:
        User: 当前登录用户对象

    Raises:
        HTTPException: 401 错误，当令牌无效或用户不存在时
    """
    from models.user import User

    # 构建认证失败的异常
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        # 解码 JWT 令牌
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        user_id = int(user_id)
    except JWTError:
        raise credentials_exception

    # 从数据库查询用户
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


async def authenticate_ws_token(token: str, db: AsyncSession) -> Optional["User"]:
    """
    WebSocket 连接的令牌认证

    与 get_current_user() 不同，此函数：
    1. 不使用 Depends() 依赖注入
    2. 失败时返回 None 而非抛出异常
    3. 适用于 WebSocket 握手阶段的手动认证

    使用场景：
        WebSocket 连接时的查询参数认证
        ws://host/ws?token=xxx

    Args:
        token: JWT 令牌字符串
        db: 数据库会话

    Returns:
        User | None: 认证成功返回用户对象，失败返回 None

    示例:
        user = await authenticate_ws_token(token, db)
        if user is None:
            await websocket.close(code=4001, reason="Unauthorized")
    """
    from models.user import User

    if not token:
        return None

    try:
        # 解码 JWT 令牌
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        user_id = int(user_id)
    except (JWTError, ValueError):
        return None

    # 从数据库查询用户
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_current_admin_user(
    current_user = Depends(get_current_user),
):
    """
    管理员权限验证的依赖注入函数

    在 get_current_user 基础上增加管理员身份验证，
    用于保护管理后台接口。

    使用场景：
        管理后台的内容审核、用户管理、数据统计等接口

    Args:
        current_user: 已认证的用户对象（来自 get_current_user）

    Returns:
        User: 当前管理员用户对象

    Raises:
        HTTPException: 403 错误，当用户不是管理员时

    示例:
        @router.get("/admin/users")
        async def list_users(admin: User = Depends(get_current_admin_user)):
            return await get_all_users()
    """
    if current_user.is_admin != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user