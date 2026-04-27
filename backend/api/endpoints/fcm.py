"""
FCM Token 管理端点模块

================================================================================
功能概述
================================================================================
本模块提供 Firebase Cloud Messaging Token 的管理 API：
- 注册/更新设备 Token
- 注销设备 Token（用户登出时）

================================================================================
API 端点列表
================================================================================
POST   /api/fcm/register   - 注册或更新 FCM Token
DELETE /api/fcm/unregister - 注销 FCM Token
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import Optional
from datetime import datetime

from core.database import get_db
from core.security import get_current_user
from models.user import User
from models.user_fcm_token import UserFcmToken

router = APIRouter(prefix="/api/fcm", tags=["fcm"])


# ── Pydantic 数据模型 ──────────────────────────────────────────

class RegisterTokenRequest(BaseModel):
    """FCM Token 注册请求"""
    token: str
    device_name: Optional[str] = None
    platform: Optional[str] = None  # "android" | "ios" | "web"


class UnregisterTokenRequest(BaseModel):
    """FCM Token 注销请求"""
    token: str


# ── API 端点 ──────────────────────────────────────────────────

@router.post("/register")
async def register_fcm_token(
    req: RegisterTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    注册或更新 FCM Token。

    如果 Token 已存在，更新其关联的用户和最后使用时间。
    如果 Token 不存在，创建新记录。

    支持多设备：同一用户可注册多个 Token。
    """
    # 查找是否已存在该 Token
    result = await db.execute(
        select(UserFcmToken).where(UserFcmToken.token == req.token)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Token 已存在：更新关联用户和最后使用时间
        existing.user_id = current_user.id
        existing.last_used_at = datetime.utcnow()
        if req.device_name:
            existing.device_name = req.device_name
        if req.platform:
            existing.platform = req.platform
    else:
        # 新 Token：创建记录
        new_token = UserFcmToken(
            user_id=current_user.id,
            token=req.token,
            device_name=req.device_name,
            platform=req.platform,
        )
        db.add(new_token)

    await db.commit()
    return {"message": "FCM token registered successfully"}


@router.delete("/unregister")
async def unregister_fcm_token(
    req: UnregisterTokenRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    注销 FCM Token。

    用户登出或卸载应用时调用，移除设备的推送能力。
    仅允许删除属于当前用户的 Token。
    """
    await db.execute(
        delete(UserFcmToken).where(
            UserFcmToken.token == req.token,
            UserFcmToken.user_id == current_user.id,
        )
    )
    await db.commit()
    return {"message": "FCM token unregistered successfully"}
