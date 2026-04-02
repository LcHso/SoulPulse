"""M7: DevOps & Model Tuning endpoints"""

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user, _to_utc_iso

router = APIRouter(tags=["admin-devops"])


class ConfigOut(BaseModel):
    id: int
    key: str
    value: str
    description: str
    updated_by: int
    updated_at: str


class ConfigUpsert(BaseModel):
    key: str
    value: str
    description: str = ""


class SandboxRequest(BaseModel):
    system_prompt: str
    user_message: str
    model: str | None = None


class AuditLogOut(BaseModel):
    id: int
    admin_user_id: int
    action: str
    target_type: str
    target_id: str
    ip_address: str
    created_at: str


# ── System Config ──

@router.get("/config")
async def list_configs(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.system_config import SystemConfig
    result = await db.execute(select(SystemConfig).order_by(SystemConfig.key))
    return [
        ConfigOut(
            id=c.id, key=c.key, value=c.value, description=c.description,
            updated_by=c.updated_by, updated_at=_to_utc_iso(c.updated_at),
        )
        for c in result.scalars().all()
    ]


@router.put("/config")
async def upsert_config(
    req: ConfigUpsert,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.system_config import SystemConfig
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == req.key))
    entry = result.scalar_one_or_none()
    if entry:
        entry.value = req.value
        entry.description = req.description
        entry.updated_by = admin.id
    else:
        entry = SystemConfig(
            key=req.key, value=req.value,
            description=req.description, updated_by=admin.id,
        )
        db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return ConfigOut(
        id=entry.id, key=entry.key, value=entry.value, description=entry.description,
        updated_by=entry.updated_by, updated_at=_to_utc_iso(entry.updated_at),
    )


@router.delete("/config/{config_key}")
async def delete_config(
    config_key: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.system_config import SystemConfig
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == config_key))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Config not found")
    await db.delete(entry)
    await db.commit()
    return {"message": "Deleted", "key": config_key}


# ── Model switch (reference only, NOT hot-reload into production) ──

@router.get("/models/current")
async def get_current_models(
    admin=Depends(get_current_admin_user),
):
    from core.config import settings
    return {
        "chat_model": settings.DASHSCOPE_CHAT_MODEL,
        "character_model": settings.DASHSCOPE_CHARACTER_MODEL,
        "image_model": settings.DASHSCOPE_IMAGE_MODEL,
        "video_model": settings.DASHSCOPE_VIDEO_MODEL,
        "embedding_model": settings.DASHSCOPE_EMBEDDING_MODEL,
    }


# ── API Usage ──

@router.get("/api-usage")
async def get_api_usage(
    days: int = 7,
    service: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.api_usage_log import ApiUsageLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    query = (
        select(ApiUsageLog)
        .where(ApiUsageLog.created_at >= cutoff)
        .order_by(ApiUsageLog.created_at.desc())
    )
    if service:
        query = query.where(ApiUsageLog.service == service)

    result = await db.execute(query.limit(limit))
    logs = result.scalars().all()
    return [
        {
            "id": l.id, "service": l.service, "model_name": l.model_name,
            "request_tokens": l.request_tokens, "response_tokens": l.response_tokens,
            "latency_ms": l.latency_ms, "success": l.success,
            "error_message": l.error_message, "cost_estimate": l.cost_estimate,
            "created_at": _to_utc_iso(l.created_at),
        }
        for l in logs
    ]


@router.get("/api-usage/summary")
async def get_api_usage_summary(
    days: int = 7,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.api_usage_log import ApiUsageLog

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(
            ApiUsageLog.service,
            func.count(ApiUsageLog.id).label("total_calls"),
            func.sum(ApiUsageLog.request_tokens).label("total_req_tokens"),
            func.sum(ApiUsageLog.response_tokens).label("total_resp_tokens"),
            func.avg(ApiUsageLog.latency_ms).label("avg_latency"),
            func.sum(ApiUsageLog.cost_estimate).label("total_cost"),
            func.sum(1 - ApiUsageLog.success).label("error_count"),
        )
        .where(ApiUsageLog.created_at >= cutoff)
        .group_by(ApiUsageLog.service)
    )
    return [
        {
            "service": row.service,
            "total_calls": row.total_calls,
            "total_request_tokens": row.total_req_tokens or 0,
            "total_response_tokens": row.total_resp_tokens or 0,
            "avg_latency_ms": round(row.avg_latency or 0, 1),
            "total_cost": round(row.total_cost or 0, 4),
            "error_count": row.error_count or 0,
        }
        for row in result.all()
    ]


# ── Prompt Sandbox (via admin_sandbox_service, NOT chat_service) ──

@router.post("/sandbox/chat")
async def sandbox_chat_endpoint(
    req: SandboxRequest,
    admin=Depends(get_current_admin_user),
):
    from services.admin_sandbox_service import sandbox_chat
    reply = await sandbox_chat(
        system_prompt=req.system_prompt,
        user_message=req.user_message,
        model=req.model,
    )
    return {"reply": reply, "model": req.model or "default"}


# ── Scheduler status ──

@router.get("/scheduler/status")
async def get_scheduler_status(
    admin=Depends(get_current_admin_user),
):
    import subprocess
    status = {}
    for svc in ["soulpulse.service", "soulpulse-scheduler.service"]:
        try:
            r = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True, timeout=5,
            )
            status[svc] = r.stdout.strip()
        except Exception:
            status[svc] = "unknown"
    return status


# ── Audit Logs ──

@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.admin_audit_log import AdminAuditLog

    query = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc())
    if action:
        query = query.where(AdminAuditLog.action == action)

    count_q = select(func.count()).select_from(AdminAuditLog)
    total = (await db.execute(count_q)).scalar() or 0

    result = await db.execute(query.offset(offset).limit(limit))
    logs = result.scalars().all()
    return {
        "logs": [
            AuditLogOut(
                id=l.id, admin_user_id=l.admin_user_id, action=l.action,
                target_type=l.target_type, target_id=l.target_id,
                ip_address=l.ip_address, created_at=_to_utc_iso(l.created_at),
            )
            for l in logs
        ],
        "total": total,
        "has_more": offset + limit < total,
    }


# ── CSV Export ──

@router.get("/audit-logs/export/csv")
async def export_audit_logs_csv(
    action: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.admin_audit_log import AdminAuditLog

    query = select(AdminAuditLog).order_by(AdminAuditLog.created_at.desc()).limit(5000)
    if action:
        query = query.where(AdminAuditLog.action == action)

    result = await db.execute(query)
    logs = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "admin_user_id", "action", "target_type", "target_id", "ip_address", "created_at"])
    for l in logs:
        writer.writerow([l.id, l.admin_user_id, l.action, l.target_type, l.target_id, l.ip_address, _to_utc_iso(l.created_at)])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )
