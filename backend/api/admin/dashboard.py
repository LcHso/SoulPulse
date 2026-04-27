"""M1: Core Dashboard endpoints"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user, _to_utc_iso

router = APIRouter(tags=["admin-dashboard"])


class AnalyticsOverview(BaseModel):
    total_users: int
    total_personas: int
    pending_posts: int
    published_posts: int
    total_messages: int
    total_stories: int
    active_users_24h: int
    online_now: int
    active_users_30d: int = 0
    dau_mau_ratio: float = 0.0
    avg_session_length_min: float = 0.0


class CharacterDistribution(BaseModel):
    ai_id: int
    ai_name: str
    message_count: int
    percentage: float


class DailyStats(BaseModel):
    date: str
    new_users: int
    messages: int
    posts_generated: int
    api_calls: int


class RetentionData(BaseModel):
    period: str
    registered: int
    returned: int
    rate: float


class LeaderboardEntry(BaseModel):
    persona_id: int
    persona_name: str
    avatar_url: str
    total_messages: int
    unique_users: int
    avg_session_length: float


# ── Migrated from old admin.py ──

@router.get("/analytics/overview")
async def get_analytics_overview(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.user import User
    from models.post import Post
    from models.ai_persona import AIPersona
    from models.chat_message import ChatMessage
    from models.story import Story

    users_r = await db.execute(select(func.count(User.id)))
    total_users = users_r.scalar() or 0

    personas_r = await db.execute(select(func.count(AIPersona.id)).where(AIPersona.is_active == 1))
    total_personas = personas_r.scalar() or 0

    pending_r = await db.execute(select(func.count(Post.id)).where(Post.status == 0))
    pending_posts = pending_r.scalar() or 0

    published_r = await db.execute(select(func.count(Post.id)).where(Post.status == 1))
    published_posts = published_r.scalar() or 0

    messages_r = await db.execute(select(func.count(ChatMessage.id)))
    total_messages = messages_r.scalar() or 0

    stories_r = await db.execute(select(func.count(Story.id)))
    total_stories = stories_r.scalar() or 0

    # Active users in last 24h (users who sent messages)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    active_r = await db.execute(
        select(func.count(func.distinct(ChatMessage.user_id)))
        .where(ChatMessage.created_at >= cutoff)
    )
    active_users_24h = active_r.scalar() or 0

    # Active users in last 30 days (MAU)
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)
    active_30d_r = await db.execute(
        select(func.count(func.distinct(ChatMessage.user_id)))
        .where(ChatMessage.created_at >= cutoff_30d)
    )
    active_users_30d = active_30d_r.scalar() or 0

    # DAU/MAU ratio (stickiness indicator)
    dau_mau_ratio = round(active_users_24h / active_users_30d * 100, 1) if active_users_30d > 0 else 0.0

    # Average session length estimate (based on message timestamps)
    # For each user-day: time between first and last message, averaged
    avg_session_length_min = await _calculate_avg_session_length(db)

    # Online now (from ws_manager)
    online_now = 0
    try:
        from core.ws_manager import ws_manager
        stats = ws_manager.get_stats()
        online_now = stats.get("total_connections", 0)
    except Exception:
        pass

    return AnalyticsOverview(
        total_users=total_users,
        total_personas=total_personas,
        pending_posts=pending_posts,
        published_posts=published_posts,
        total_messages=total_messages,
        total_stories=total_stories,
        active_users_24h=active_users_24h,
        online_now=online_now,
        active_users_30d=active_users_30d,
        dau_mau_ratio=dau_mau_ratio,
        avg_session_length_min=avg_session_length_min,
    )


@router.get("/analytics/daily-stats")
async def get_daily_stats(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.user import User
    from models.chat_message import ChatMessage
    from models.post import Post

    results = []
    now = datetime.now(timezone.utc)
    for i in range(days):
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        new_users_r = await db.execute(
            select(func.count(User.id)).where(User.created_at >= day_start, User.created_at < day_end)
        )
        msgs_r = await db.execute(
            select(func.count(ChatMessage.id)).where(ChatMessage.created_at >= day_start, ChatMessage.created_at < day_end)
        )
        posts_r = await db.execute(
            select(func.count(Post.id)).where(Post.created_at >= day_start, Post.created_at < day_end)
        )

        # API calls from api_usage_logs if table exists
        api_calls = 0
        try:
            from models.api_usage_log import ApiUsageLog
            api_r = await db.execute(
                select(func.count(ApiUsageLog.id)).where(ApiUsageLog.created_at >= day_start, ApiUsageLog.created_at < day_end)
            )
            api_calls = api_r.scalar() or 0
        except Exception:
            pass

        results.append(DailyStats(
            date=day_start.strftime("%Y-%m-%d"),
            new_users=new_users_r.scalar() or 0,
            messages=msgs_r.scalar() or 0,
            posts_generated=posts_r.scalar() or 0,
            api_calls=api_calls,
        ))

    return results


@router.get("/analytics/retention")
async def get_retention(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.user import User
    from models.chat_message import ChatMessage

    now = datetime.now(timezone.utc)
    periods = [
        ("Day 1", 1), ("Day 3", 3), ("Day 7", 7), ("Day 14", 14), ("Day 30", 30)
    ]
    results = []
    for label, days in periods:
        # Users who registered at least `days` ago
        reg_cutoff = now - timedelta(days=days)
        reg_r = await db.execute(
            select(func.count(User.id)).where(User.created_at <= reg_cutoff)
        )
        registered = reg_r.scalar() or 0
        if registered == 0:
            results.append(RetentionData(period=label, registered=0, returned=0, rate=0.0))
            continue

        # Among those users, count how many were active in the past `days` days
        # Active = sent at least one message in the period
        activity_cutoff = now - timedelta(days=days)
        ret_r = await db.execute(
            select(func.count(func.distinct(ChatMessage.user_id)))
            .where(ChatMessage.created_at >= activity_cutoff)
            .where(ChatMessage.user_id.in_(
                select(User.id).where(User.created_at <= reg_cutoff)
            ))
        )
        returned = ret_r.scalar() or 0
        results.append(RetentionData(
            period=label,
            registered=registered,
            returned=returned,
            rate=round(returned / registered * 100, 1) if registered else 0.0,
        ))

    return results


@router.get("/analytics/leaderboard")
async def get_ai_leaderboard(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.ai_persona import AIPersona
    from models.chat_message import ChatMessage

    # Get message counts per persona
    stmt = (
        select(
            ChatMessage.ai_id,
            func.count(ChatMessage.id).label("total_messages"),
            func.count(func.distinct(ChatMessage.user_id)).label("unique_users"),
        )
        .group_by(ChatMessage.ai_id)
        .order_by(func.count(ChatMessage.id).desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    rows = result.all()

    entries = []
    for ai_id, total_msgs, unique_users in rows:
        p_r = await db.execute(select(AIPersona).where(AIPersona.id == ai_id))
        persona = p_r.scalar_one_or_none()
        if persona:
            entries.append(LeaderboardEntry(
                persona_id=persona.id,
                persona_name=persona.name,
                avatar_url=persona.avatar_url,
                total_messages=total_msgs,
                unique_users=unique_users,
                avg_session_length=0.0,
            ))

    return entries


@router.get("/analytics/realtime")
async def get_realtime_stats(
    admin=Depends(get_current_admin_user),
):
    stats = {"total_connections": 0, "per_persona": {}}
    try:
        from core.ws_manager import ws_manager
        stats = ws_manager.get_stats()
    except Exception:
        pass
    return stats


@router.get("/analytics/errors")
async def get_recent_errors(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    try:
        from models.api_usage_log import ApiUsageLog
        result = await db.execute(
            select(ApiUsageLog)
            .where(ApiUsageLog.success == 0)
            .order_by(ApiUsageLog.created_at.desc())
            .limit(limit)
        )
        logs = result.scalars().all()
        return [
            {
                "id": l.id,
                "service": l.service,
                "model_name": l.model_name,
                "error_message": l.error_message,
                "latency_ms": l.latency_ms,
                "created_at": _to_utc_iso(l.created_at),
            }
            for l in logs
        ]
    except Exception:
        return []


@router.get("/analytics/character-distribution")
async def get_character_distribution(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """Get message distribution per AI character."""
    from models.ai_persona import AIPersona
    from models.chat_message import ChatMessage

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get message counts per AI
    stmt = (
        select(
            ChatMessage.ai_id,
            func.count(ChatMessage.id).label("message_count"),
        )
        .where(ChatMessage.created_at >= cutoff)
        .group_by(ChatMessage.ai_id)
        .order_by(func.count(ChatMessage.id).desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    # Calculate total
    total_messages = sum(row.message_count for row in rows)

    # Get persona names
    entries = []
    for row in rows:
        ai_id = row.ai_id
        message_count = row.message_count
        percentage = round(message_count / total_messages * 100, 1) if total_messages > 0 else 0.0

        # Get persona name
        p_r = await db.execute(select(AIPersona.name).where(AIPersona.id == ai_id))
        name = p_r.scalar_one_or_none() or f"AI #{ai_id}"

        entries.append(CharacterDistribution(
            ai_id=ai_id,
            ai_name=name,
            message_count=message_count,
            percentage=percentage,
        ))

    return entries


async def _calculate_avg_session_length(db: AsyncSession) -> float:
    """
    Calculate average session length in minutes.

    Estimates from message timestamps:
    - For each user-day: time between first and last message
    - Average across all user-days in the past 30 days
    """
    from models.chat_message import ChatMessage

    # Get all messages from past 30 days, grouped by user and date
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Query to get first and last message time per user per day
    # Using raw SQL for efficiency
    query = text("""
        SELECT
            user_id,
            DATE(created_at) as msg_date,
            MIN(created_at) as first_msg,
            MAX(created_at) as last_msg
        FROM chat_messages
        WHERE created_at >= :cutoff
        GROUP BY user_id, DATE(created_at)
        HAVING COUNT(*) > 1
    """)

    try:
        result = await db.execute(query, {"cutoff": cutoff})
        rows = result.fetchall()

        if not rows:
            return 0.0

        total_minutes = 0.0
        for row in rows:
            first_msg = row.first_msg
            last_msg = row.last_msg
            if first_msg and last_msg:
                diff = (last_msg - first_msg).total_seconds() / 60.0
                total_minutes += diff

        return round(total_minutes / len(rows), 1) if rows else 0.0
    except Exception:
        return 0.0

