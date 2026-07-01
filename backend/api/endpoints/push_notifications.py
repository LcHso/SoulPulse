"""
推送系统 API 端点模块

================================================================================
功能概述
================================================================================
本模块提供推送通知系统的外部 API：
- 设备注册：注册/更新用户设备的推送 Token
- 通知偏好查询：获取用户的通知设置
- 通知偏好更新：部分更新用户的通知设置

================================================================================
API 端点列表
================================================================================
POST   /api/v1/devices/register                     - 注册设备推送 Token
GET    /api/v1/users/{user_id}/notification-preferences  - 获取通知偏好
PATCH  /api/v1/users/{user_id}/notification-preferences  - 更新通知偏好
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from core.database import get_db
from core.security import get_current_user
from core.utils import to_utc_iso
from models.user import User
from models.notification_preference import NotificationPreference
from models.user_device import UserDevice

router = APIRouter(prefix="/api/v1", tags=["push-notifications"])


# ── Pydantic 数据模型（请求/响应 Schema）──────────────────────────

class DeviceRegisterRequest(BaseModel):
    """设备注册请求"""
    platform: str            # "ios" | "android" | "web"
    push_token: str          # 推送 Token 字符串
    device_name: Optional[str] = None  # 设备名称（可选）


class DeviceRegisterResponse(BaseModel):
    """设备注册响应"""
    device_id: int
    registered: bool = True


class NotificationPreferencesOut(BaseModel):
    """通知偏好输出"""
    new_post: bool = True
    proactive_dm: bool = True
    new_story: bool = True
    comment_reply: bool = True
    intimacy_event: bool = True
    quiet_hour_start: Optional[str] = None
    quiet_hour_end: Optional[str] = None
    per_character_overrides: dict = {}


class NotificationPreferencesUpdate(BaseModel):
    """通知偏好部分更新请求（所有字段均可选）"""
    new_post: Optional[bool] = None
    proactive_dm: Optional[bool] = None
    new_story: Optional[bool] = None
    comment_reply: Optional[bool] = None
    intimacy_event: Optional[bool] = None
    quiet_hour_start: Optional[str] = None
    quiet_hour_end: Optional[str] = None
    per_character_overrides: Optional[dict] = None


class NotificationPreferencesUpdateResponse(BaseModel):
    """通知偏好更新响应"""
    updated: bool = True
    preferences: NotificationPreferencesOut


# ── 辅助函数 ──────────────────────────────────────────────────

def _pref_to_out(pref: NotificationPreference) -> NotificationPreferencesOut:
    """将 ORM 模型转为输出 Schema。"""
    overrides = {}
    if pref.per_character_overrides:
        try:
            overrides = json.loads(pref.per_character_overrides) if isinstance(
                pref.per_character_overrides, str
            ) else pref.per_character_overrides
        except (json.JSONDecodeError, TypeError):
            overrides = {}

    return NotificationPreferencesOut(
        new_post=pref.new_post,
        proactive_dm=pref.proactive_dm,
        new_story=pref.new_story,
        comment_reply=pref.comment_reply,
        intimacy_event=pref.intimacy_event,
        quiet_hour_start=pref.quiet_hour_start.strftime("%H:%M") if pref.quiet_hour_start else None,
        quiet_hour_end=pref.quiet_hour_end.strftime("%H:%M") if pref.quiet_hour_end else None,
        per_character_overrides=overrides,
    )


async def _ensure_preference(db: AsyncSession, user_id: int) -> NotificationPreference:
    """获取用户偏好，不存在时自动创建默认值。"""
    result = await db.execute(
        select(NotificationPreference).where(
            NotificationPreference.user_id == user_id,
        )
    )
    pref = result.scalar_one_or_none()
    if pref is None:
        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        await db.flush()
    return pref


# ── API 端点 ──────────────────────────────────────────────────

@router.post("/devices/register", response_model=DeviceRegisterResponse)
async def register_device(
    req: DeviceRegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    注册或更新设备推送 Token。

    如果 (user_id, push_token) 已存在，更新其平台和设备名称。
    如果不存在，创建新记录。同一 token 不允许跨用户共享。
    """
    # 验证平台值
    if req.platform not in ("ios", "android", "web"):
        raise HTTPException(status_code=400, detail="platform must be ios, android, or web")

    # 查找是否已有该 token 的记录
    result = await db.execute(
        select(UserDevice).where(UserDevice.push_token == req.push_token)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Token 已存在：更新归属用户和设备信息
        existing.user_id = current_user.id
        existing.platform = req.platform
        existing.device_name = req.device_name
        existing.is_active = True
        await db.commit()
        await db.refresh(existing)
        return DeviceRegisterResponse(device_id=existing.id)

    # 新 Token：创建记录
    device = UserDevice(
        user_id=current_user.id,
        platform=req.platform,
        push_token=req.push_token,
        device_name=req.device_name,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return DeviceRegisterResponse(device_id=device.id)


@router.get(
    "/users/{user_id}/notification-preferences",
    response_model=NotificationPreferencesOut,
)
async def get_notification_preferences(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取用户的通知偏好设置。

    仅允许查询自己的偏好（user_id 必须与当前登录用户一致）。
    如果偏好不存在，自动创建默认值（全部开启）。
    """
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot access other user's preferences")

    pref = await _ensure_preference(db, user_id)
    return _pref_to_out(pref)


@router.patch(
    "/users/{user_id}/notification-preferences",
    response_model=NotificationPreferencesUpdateResponse,
)
async def update_notification_preferences(
    user_id: int,
    body: NotificationPreferencesUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    部分更新用户的通知偏好设置。

    仅允许修改自己的偏好。只传入需要修改的字段，
    未传入的字段保持不变。

    时间格式：quiet_hour_start / quiet_hour_end 使用 "HH:MM" 格式，
    传入空字符串 "" 表示清除免打扰设置。
    """
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot modify other user's preferences")

    pref = await _ensure_preference(db, user_id)

    # 逐个更新非 None 字段
    bool_fields = ["new_post", "proactive_dm", "new_story", "comment_reply", "intimacy_event"]
    for field in bool_fields:
        value = getattr(body, field, None)
        if value is not None:
            setattr(pref, field, value)

    # 免打扰时间
    if body.quiet_hour_start is not None:
        if body.quiet_hour_start == "":
            pref.quiet_hour_start = None
        else:
            try:
                h, m = body.quiet_hour_start.split(":")
                from datetime import time
                pref.quiet_hour_start = time(int(h), int(m))
            except (ValueError, AttributeError):
                raise HTTPException(status_code=400, detail="quiet_hour_start format must be HH:MM")

    if body.quiet_hour_end is not None:
        if body.quiet_hour_end == "":
            pref.quiet_hour_end = None
        else:
            try:
                h, m = body.quiet_hour_end.split(":")
                from datetime import time
                pref.quiet_hour_end = time(int(h), int(m))
            except (ValueError, AttributeError):
                raise HTTPException(status_code=400, detail="quiet_hour_end format must be HH:MM")

    # 角色覆盖配置
    if body.per_character_overrides is not None:
        pref.per_character_overrides = json.dumps(body.per_character_overrides)

    await db.commit()
    await db.refresh(pref)

    return NotificationPreferencesUpdateResponse(
        updated=True,
        preferences=_pref_to_out(pref),
    )
