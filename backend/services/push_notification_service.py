"""
SoulPulse 推送通知服务

统一的推送通知发送入口，负责：
1. 检查用户通知偏好（是否开启该类型通知）
2. 检查免打扰时段（quiet hours）
3. 检查按角色覆盖设置（per_character_overrides）
4. 获取用户活跃设备 Token
5. 发送推送（当前为日志模拟，后续接入 FCM/APNs）
6. 写入通知日志（notification_log）

依赖注入使用方式：
    from services.push_notification_service import get_push_service

    @router.post("/some-action")
    async def some_action(push: PushNotificationService = Depends(get_push_service)):
        await push.send(user_id=1, type="new_post", title="...", body="...")

Deep Link 路由表：
    new_post       → /feed?highlight_post={post_id}
    proactive_dm   → /chat/{character_id}
    new_story      → /stories/{character_id}
    comment_reply  → /posts/{post_id}?scroll_to_comment={comment_id}
    intimacy_event → /profile/{character_id}/relationship
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session

logger = logging.getLogger(__name__)

# ── Deep Link 路由模板 ──────────────────────────────────────────
# key = notification type, value = deep_link 模板函数
DEEP_LINK_ROUTES: dict[str, str] = {
    "new_post": "/feed?highlight_post={post_id}",
    "proactive_dm": "/chat/{character_id}",
    "new_story": "/stories/{character_id}",
    "comment_reply": "/posts/{post_id}?scroll_to_comment={comment_id}",
    "intimacy_event": "/profile/{character_id}/relationship",
}

# 通知类型 → NotificationPreference 字段名的映射
_TYPE_TO_PREF_FIELD: dict[str, str] = {
    "new_post": "new_post",
    "proactive_dm": "proactive_dm",
    "new_story": "new_story",
    "comment_reply": "comment_reply",
    "intimacy_event": "intimacy_event",
}


def build_deep_link(
    notification_type: str,
    character_id: Optional[int] = None,
    post_id: Optional[int] = None,
    comment_id: Optional[int] = None,
) -> str:
    """根据通知类型和关联 ID 构建 deep link。

    Args:
        notification_type: 通知类型
        character_id: 关联角色 ID
        post_id: 关联帖子 ID
        comment_id: 关联评论 ID

    Returns:
        str: 构建好的 deep link，未知类型时返回空字符串
    """
    template = DEEP_LINK_ROUTES.get(notification_type, "")
    if not template:
        return ""
    return template.format(
        character_id=character_id or "",
        post_id=post_id or "",
        comment_id=comment_id or "",
    )


class PushNotificationService:
    """
    推送通知服务

    提供统一的 send() 方法，内部完成偏好检查、免打扰判断、
    设备 Token 获取、推送发送（日志模拟）和日志记录。

    可通过 FastAPI Depends() 注入使用，也可直接实例化使用。
    """

    async def send(
        self,
        user_id: int,
        type: str,
        title: str,
        body: str,
        character_id: Optional[int] = None,
        deep_link: str = "",
        db: Optional[AsyncSession] = None,
    ) -> bool:
        """
        发送推送通知。

        完整流程：
        1. 检查 notification_preferences（用户是否开启该类型通知）
        2. 检查 quiet_hour（是否在免打扰时间）
        3. 检查 per_character_overrides（角色级别覆盖）
        4. 获取 user_devices 中 is_active=True 的 token
        5. 发送推送（FCM/APNs — 当前为日志模拟）
        6. 写入 notification_log

        Args:
            user_id: 目标用户 ID
            type: 通知类型（new_post/proactive_dm/new_story/comment_reply/intimacy_event）
            title: 通知标题
            body: 通知正文
            character_id: 关联 AI 角色 ID（可选）
            deep_link: 应用内跳转链接（可选，为空时自动生成）
            db: 数据库会话（可选，为空时自动创建）

        Returns:
            bool: 推送是否成功发送
        """
        owned_session = False
        if db is None:
            db = async_session()
            await db.__aenter__()
            owned_session = True

        try:
            # ── Step 1: 检查通知偏好 ──────────────────────────────────
            pref = await self._get_preference(db, user_id)
            if pref is None:
                logger.info("[PushService] No preference found for user %s, creating defaults", user_id)
                pref = await self._create_default_preference(db, user_id)

            # 检查该类型通知是否开启
            pref_field = _TYPE_TO_PREF_FIELD.get(type)
            if pref_field and not getattr(pref, pref_field, True):
                logger.info("[PushService] User %s disabled %s notifications", user_id, type)
                return False

            # ── Step 2: 检查免打扰时段 ──────────────────────────────────
            if self._is_quiet_hour(pref.quiet_hour_start, pref.quiet_hour_end):
                logger.info("[PushService] User %s in quiet hours, suppressing push", user_id)
                return False

            # ── Step 3: 检查按角色覆盖 ──────────────────────────────────
            if character_id and pref.per_character_overrides:
                if self._is_character_blocked(pref.per_character_overrides, character_id, type):
                    logger.info(
                        "[PushService] User %s blocked %s for character %s",
                        user_id, type, character_id,
                    )
                    return False

            # ── Step 4: 获取活跃设备 Token ──────────────────────────────────
            devices = await self._get_active_devices(db, user_id)
            if not devices:
                logger.info("[PushService] No active devices for user %s", user_id)
                # 即使没有设备也记录日志，便于分析

            # ── Step 5: 发送推送（日志模拟）──────────────────────────────────
            # 自动生成 deep_link（如果未提供）
            if not deep_link:
                deep_link = build_deep_link(type, character_id=character_id)

            for device in devices:
                await self._dispatch_push(
                    platform=device.platform,
                    token=device.push_token,
                    title=title,
                    body=body,
                    data={
                        "type": type,
                        "deep_link": deep_link,
                        "character_id": str(character_id) if character_id else "",
                    },
                )

            # ── Step 6: 写入通知日志 ──────────────────────────────────
            await self._write_log(
                db, user_id=user_id, type=type, title=title, body=body,
                character_id=character_id, deep_link=deep_link,
            )
            await db.commit()

            logger.info(
                "[PushService] Sent %s to user %s (%d devices): %s",
                type, user_id, len(devices), title,
            )
            return True

        except Exception as exc:
            logger.error("[PushService] Failed to send push to user %s: %s", user_id, exc)
            return False

        finally:
            if owned_session:
                try:
                    await db.__aexit__(None, None, None)
                except Exception:
                    pass

    # ── 内部方法 ──────────────────────────────────────────────────

    async def _get_preference(self, db: AsyncSession, user_id: int):
        """查询用户通知偏好，不存在时返回 None。"""
        from models.notification_preference import NotificationPreference

        result = await db.execute(
            select(NotificationPreference).where(
                NotificationPreference.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _create_default_preference(self, db: AsyncSession, user_id: int):
        """为用户创建默认通知偏好（全部开启）。"""
        from models.notification_preference import NotificationPreference

        pref = NotificationPreference(user_id=user_id)
        db.add(pref)
        await db.flush()
        return pref

    @staticmethod
    def _is_quiet_hour(start: Optional[time], end: Optional[time]) -> bool:
        """判断当前时间是否在免打扰时段。"""
        if start is None or end is None:
            return False

        now = datetime.now(timezone.utc).time()

        if start <= end:
            # 同日区间，如 23:00 ~ 07:00 不适用此分支
            # 正常区间如 22:00 ~ 06:00 → 需要跨日处理
            return start <= now < end
        else:
            # 跨日区间，如 23:00 ~ 07:00
            # 当前时间 >= 23:00 或 < 07:00 都算免打扰
            return now >= start or now < end

    @staticmethod
    def _is_character_blocked(overrides_json: str, character_id: int, notification_type: str) -> bool:
        """检查 per_character_overrides 中该角色是否屏蔽了该通知类型。"""
        try:
            overrides = json.loads(overrides_json) if isinstance(overrides_json, str) else overrides_json
            char_key = str(character_id)
            char_overrides = overrides.get(char_key, {})
            # 如果角色配置中明确将某类型设为 False，则屏蔽
            pref_field = _TYPE_TO_PREF_FIELD.get(notification_type)
            if pref_field and char_overrides.get(pref_field) is False:
                return True
        except (json.JSONDecodeError, TypeError):
            pass
        return False

    async def _get_active_devices(self, db: AsyncSession, user_id: int) -> list:
        """查询用户的所有活跃设备。"""
        from models.user_device import UserDevice

        result = await db.execute(
            select(UserDevice).where(
                UserDevice.user_id == user_id,
                UserDevice.is_active == True,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def _dispatch_push(
        platform: str,
        token: str,
        title: str,
        body: str,
        data: Optional[dict] = None,
    ) -> bool:
        """
        发送推送通知（日志模拟实现）。

        当前仅打印推送内容到日志，后续可接入：
        - FCM (Android/Web): firebase_admin.messaging
        - APNs (iOS): aioapns / hyper-push
        - Web Push: pywebpush

        Returns:
            bool: 模拟发送始终返回 True
        """
        logger.info(
            "[PushService][%s] → token=%.20s... | title=%s | body=%s | data=%s",
            platform.upper(), token, title, body[:80], data,
        )
        # TODO: 接入真实推送服务
        # if platform == "android" or platform == "web":
        #     from services.fcm_service import send_push_notification
        #     return await send_push_notification(token, title, body, data)
        # elif platform == "ios":
        #     # APNs integration
        #     pass
        return True

    async def _write_log(
        self,
        db: AsyncSession,
        user_id: int,
        type: str,
        title: str,
        body: str,
        character_id: Optional[int],
        deep_link: str,
    ):
        """写入通知日志到 notification_log 表。"""
        from models.notification_log import NotificationLog

        log = NotificationLog(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            character_id=character_id,
            deep_link=deep_link,
        )
        db.add(log)


# ── FastAPI 依赖注入 ──────────────────────────────────────────

# 模块级单例
_push_service_instance: Optional[PushNotificationService] = None


def get_push_service() -> PushNotificationService:
    """
    获取 PushNotificationService 实例的依赖函数。

    用于 FastAPI 路由的 Depends()：
        @router.post("/send")
        async def send(push: PushNotificationService = Depends(get_push_service)):
            await push.send(...)

    Returns:
        PushNotificationService: 推送服务单例
    """
    global _push_service_instance
    if _push_service_instance is None:
        _push_service_instance = PushNotificationService()
    return _push_service_instance
