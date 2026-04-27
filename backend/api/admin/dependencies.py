import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from functools import wraps

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user

logger = logging.getLogger("soulpulse.admin")


# ── In-memory rate limiter ──

_rate_limit_store: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 120  # max requests per window per user


async def rate_limit(request: Request):
    """Simple sliding-window rate limiter keyed by client IP."""
    client_ip = request.client.host if request.client else "unknown"
    key = f"admin:{client_ip}"
    now = time.monotonic()
    timestamps = _rate_limit_store[key]
    # Prune expired entries
    _rate_limit_store[key] = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limit_store[key]) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {_RATE_LIMIT_MAX} requests per {_RATE_LIMIT_WINDOW}s.",
        )
    _rate_limit_store[key].append(now)


async def get_current_admin_user(
    current_user=Depends(get_current_user),
):
    if current_user.is_admin != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


def audit_log(action: str, target_type: str):
    """Decorator to automatically create audit log entries for admin actions."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            # Best-effort audit logging
            try:
                request: Request = kwargs.get("request")
                admin = kwargs.get("admin")
                db: AsyncSession = kwargs.get("db")
                if db and admin:
                    from models.admin_audit_log import AdminAuditLog
                    ip = request.client.host if request and request.client else ""
                    target_id = ""
                    for key in ("persona_id", "post_id", "user_id", "entry_id", "config_id", "memory_id"):
                        if key in kwargs:
                            target_id = str(kwargs[key])
                            break
                    db.add(AdminAuditLog(
                        admin_user_id=admin.id,
                        action=action,
                        target_type=target_type,
                        target_id=target_id,
                        ip_address=ip,
                    ))
                    await db.flush()
            except Exception as e:
                logger.warning("Audit log failed: %s", e)
            return result
        return wrapper
    return decorator


def _to_utc_iso(dt: datetime) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
