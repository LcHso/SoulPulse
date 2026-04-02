"""
Admin API monitor - Standalone middleware for logging API calls.
Records on admin-backend only, does NOT modify any existing service.
"""

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("soulpulse.admin.monitor")


class AdminApiMonitorMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs API call metrics to api_usage_logs table.
    Only installed on admin-backend (port 8002), not on main backend.
    """

    async def dispatch(self, request: Request, call_next):
        # Only monitor /api/ requests
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        start = time.time()
        response = await call_next(request)
        latency_ms = int((time.time() - start) * 1000)

        # Best-effort logging - don't block request on failures
        try:
            from core.database import async_session
            from models.api_usage_log import ApiUsageLog

            async with async_session() as db:
                db.add(ApiUsageLog(
                    service="admin-api",
                    model_name=request.url.path,
                    latency_ms=latency_ms,
                    success=1 if response.status_code < 400 else 0,
                    error_message="" if response.status_code < 400 else f"HTTP {response.status_code}",
                ))
                await db.commit()
        except Exception as e:
            logger.debug("API monitor log failed: %s", e)

        return response
