"""Firebase Cloud Messaging service for sending push notifications.

This service handles:
- Storing FCM tokens for users
- Sending push notifications to specific users
- Sending broadcast notifications to topics

SETUP REQUIRED:
1. Create Firebase project at https://console.firebase.google.com/
2. Generate private key: Project Settings -> Service Accounts -> Generate Private Key
3. Save the JSON file as 'firebase-service-account.json' in the backend directory
4. Add to .env: FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# FCM service instance (lazy loaded)
_fcm_instance = None


def _get_fcm_app():
    """Get or initialize Firebase app. Returns None if not configured."""
    global _fcm_instance

    if _fcm_instance is not None:
        return _fcm_instance

    try:
        import firebase_admin
        from firebase_admin import credentials
        from core.config import settings

        # Check for service account file
        service_account_path = getattr(settings, 'FIREBASE_SERVICE_ACCOUNT_PATH', None)
        if not service_account_path:
            logger.warning("[FCM] FIREBASE_SERVICE_ACCOUNT_PATH not configured")
            return None

        path = Path(service_account_path)
        if not path.exists():
            logger.warning(f"[FCM] Service account file not found: {path}")
            return None

        # Initialize Firebase
        cred = credentials.Certificate(str(path))
        _fcm_instance = firebase_admin.initialize_app(cred)
        logger.info("[FCM] Firebase initialized successfully")
        return _fcm_instance

    except ImportError:
        logger.warning("[FCM] firebase-admin not installed. Run: pip install firebase-admin")
        return None
    except Exception as e:
        logger.error(f"[FCM] Failed to initialize Firebase: {e}")
        return None


async def send_push_notification(
    token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> bool:
    """Send a push notification to a specific device.

    Args:
        token: FCM device token
        title: Notification title
        body: Notification body
        data: Optional data payload

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        from firebase_admin import messaging

        app = _get_fcm_app()
        if app is None:
            logger.warning("[FCM] Firebase not configured, skipping push")
            return False

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    icon='ic_launcher',
                    channel_id='soulpulse_fcm',
                    priority='high',
                ),
            ),
        )

        response = messaging.send(message, app=app)
        logger.info(f"[FCM] Message sent: {response}")
        return True

    except Exception as e:
        logger.error(f"[FCM] Failed to send notification: {e}")
        return False


async def send_push_to_user(
    user_id: int,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> bool:
    """Send push notification to all devices for a user.

    Args:
        user_id: User ID
        title: Notification title
        body: Notification body
        data: Optional data payload

    Returns:
        True if sent to at least one device
    """
    from sqlalchemy import select
    from core.database import async_session
    from models.user_fcm_token import UserFcmToken

    async with async_session() as db:
        result = await db.execute(
            select(UserFcmToken).where(UserFcmToken.user_id == user_id)
        )
        tokens = result.scalars().all()

        if not tokens:
            logger.info(f"[FCM] No FCM tokens for user {user_id}")
            return False

        success_count = 0
        for token_record in tokens:
            if await send_push_notification(token_record.token, title, body, data):
                success_count += 1

        return success_count > 0


async def send_topic_message(
    topic: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> bool:
    """Send a message to all devices subscribed to a topic.

    Args:
        topic: Topic name
        title: Notification title
        body: Notification body
        data: Optional data payload

    Returns:
        True if sent successfully
    """
    try:
        from firebase_admin import messaging

        app = _get_fcm_app()
        if app is None:
            return False

        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            topic=topic,
            android=messaging.AndroidConfig(
                priority='high',
            ),
        )

        response = messaging.send(message, app=app)
        logger.info(f"[FCM] Topic message sent: {response}")
        return True

    except Exception as e:
        logger.error(f"[FCM] Failed to send topic message: {e}")
        return False


# Check if FCM is available
def is_fcm_available() -> bool:
    """Check if FCM is properly configured."""
    return _get_fcm_app() is not None


# ─────────────────────────────────────────────────────────────────────────
# Personalized push notifications (Plan Task 6.4)
# ─────────────────────────────────────────────────────────────────────────

# Maximum personalized push notifications per (user, persona) per day.
_PERSONALIZED_DAILY_CAP = 3
# Push notifications are only delivered between these local hours (inclusive
# of the lower bound, exclusive of the upper bound).
_QUIET_HOURS = (7, 23)  # 07:00 – 23:00


async def send_personalized_notification(
    user_id: int,
    persona_id: int,
    message: str,
    notification_type: str,
    db=None,
) -> bool:
    """Send a personalized push notification with emotion / time awareness.

    Enhancements over :func:`send_push_to_user`:
        * Time check — honour the persona's local timezone quiet hours
          (skip 23:00–07:00).
        * Daily frequency cap — at most ``_PERSONALIZED_DAILY_CAP``
          personalized pushes per (user, persona) per UTC day.
        * Persona-themed styling — the notification title is the persona's
          display name; the body is the supplied message; the persona's
          current emotion state subtly adjusts the body (a soft prefix when
          longing is high).

    Args:
        user_id: Recipient user id.
        persona_id: Persona originating the message.
        message: Body text of the notification.
        notification_type: Logical type label (e.g. ``"ritual_morning"``,
            ``"streak_reward"``, ``"longing_dm"``) — stored in ``data`` and
            used for daily-cap accounting.
        db: Optional existing async session. When omitted, a temporary
            session is opened (read-only style usage).

    Returns:
        bool: ``True`` if the notification was dispatched, ``False`` if it
        was suppressed (quiet hours / frequency cap / no tokens) or failed.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, func as sqlfunc

    # Lazy imports to avoid circular imports at module load time.
    from core.database import async_session
    from models.ai_persona import AIPersona
    from models.notification import Notification

    owned_session = False
    if db is None:
        db = async_session()
        owned_session = True
        await db.__aenter__()

    try:
        persona = (await db.execute(
            select(AIPersona).where(AIPersona.id == persona_id)
        )).scalar_one_or_none()
        if persona is None:
            logger.info(
                "[FCM] persona %s missing for personalized notification", persona_id,
            )
            return False

        # ── Quiet hours check (persona's local timezone) ─────────────────
        try:
            import pytz
            tz_name = getattr(persona, "timezone", None) or "UTC"
            tz = pytz.timezone(tz_name)
            local_hour = datetime.now(tz).hour
        except Exception:
            local_hour = datetime.utcnow().hour

        if not (_QUIET_HOURS[0] <= local_hour < _QUIET_HOURS[1]):
            logger.info(
                "[FCM] suppress personalized push for user=%s persona=%s "
                "(quiet hours, local_hour=%s)",
                user_id, persona_id, local_hour,
            )
            return False

        # ── Daily frequency cap ─────────────────────────────────
        # Approximation: count notifications created in the last 24h
        # whose ``data_json`` mentions this persona id.
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        # SQLite-friendly substring search on data_json text payload.
        persona_tag = f'"ai_id": {persona_id}'
        count_q = await db.execute(
            select(sqlfunc.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.created_at >= cutoff,
                Notification.data_json.contains(persona_tag),
            )
        )
        sent_today = int(count_q.scalar() or 0)
        if sent_today >= _PERSONALIZED_DAILY_CAP:
            logger.info(
                "[FCM] suppress personalized push for user=%s persona=%s "
                "(daily cap reached: %s)",
                user_id, persona_id, sent_today,
            )
            return False

        # ── Persona-aware body styling ─────────────────────────────
        body_text = message or ""
        try:
            from models.emotion_state import EmotionState
            state = (await db.execute(
                select(EmotionState).where(
                    EmotionState.user_id == user_id,
                    EmotionState.ai_id == persona_id,
                )
            )).scalar_one_or_none()
            if state is not None:
                if float(state.longing or 0.0) > 0.7 and not body_text.startswith("…"):
                    body_text = f"…{body_text}"
                elif float(state.pleasure or 0.0) > 0.5 and not body_text.endswith("。"):
                    body_text = f"{body_text}"
        except Exception as exc:
            logger.debug("[FCM] emotion lookup for personalization failed: %s", exc)

        title = persona.name or f"Persona {persona_id}"
        data_payload = {
            "ai_id": str(persona_id),
            "ai_name": persona.name or "",
            "notification_type": notification_type,
        }
        return await send_push_to_user(
            user_id=user_id,
            title=title,
            body=body_text[:200],
            data=data_payload,
        )
    finally:
        if owned_session:
            try:
                await db.__aexit__(None, None, None)
            except Exception:
                pass