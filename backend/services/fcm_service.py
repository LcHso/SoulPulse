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