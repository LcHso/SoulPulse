"""M6: Commercial Operations endpoints"""

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user, _to_utc_iso

router = APIRouter(tags=["admin-commerce"])


class GachaScriptOut(BaseModel):
    id: int
    title: str
    persona_id: int
    storyline_json: str
    system_prompt_override: str
    gem_cost: int
    is_active: int
    created_by: int
    created_at: str


class GachaCreate(BaseModel):
    title: str
    persona_id: int
    storyline_json: str = "[]"
    system_prompt_override: str = ""
    gem_cost: int = 10
    is_active: int = 1


class GiftOut(BaseModel):
    id: int
    name: str
    icon_url: str
    energy_recovery: float
    gem_cost: int
    category: str
    is_active: int
    sort_order: int


class GiftCreate(BaseModel):
    name: str
    icon_url: str = ""
    energy_recovery: float = 0.0
    gem_cost: int = 1
    category: str = "general"
    is_active: int = 1
    sort_order: int = 0


class TransactionOut(BaseModel):
    id: int
    user_id: int
    amount: int
    balance_after: int
    tx_type: str
    reference_id: str
    description: str
    created_at: str


# ── Gacha Scripts ──

@router.get("/gacha")
async def list_gacha(
    persona_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.gacha_script import GachaScript
    query = select(GachaScript).order_by(GachaScript.created_at.desc())
    if persona_id:
        query = query.where(GachaScript.persona_id == persona_id)
    result = await db.execute(query.offset(offset).limit(limit))
    return [
        GachaScriptOut(
            id=g.id, title=g.title, persona_id=g.persona_id,
            storyline_json=g.storyline_json, system_prompt_override=g.system_prompt_override,
            gem_cost=g.gem_cost, is_active=g.is_active, created_by=g.created_by,
            created_at=_to_utc_iso(g.created_at),
        )
        for g in result.scalars().all()
    ]


@router.post("/gacha")
async def create_gacha(
    req: GachaCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.gacha_script import GachaScript
    entry = GachaScript(**req.model_dump(), created_by=admin.id)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return GachaScriptOut(
        id=entry.id, title=entry.title, persona_id=entry.persona_id,
        storyline_json=entry.storyline_json, system_prompt_override=entry.system_prompt_override,
        gem_cost=entry.gem_cost, is_active=entry.is_active, created_by=entry.created_by,
        created_at=_to_utc_iso(entry.created_at),
    )


@router.put("/gacha/{gacha_id}")
async def update_gacha(
    gacha_id: int,
    req: GachaCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.gacha_script import GachaScript
    result = await db.execute(select(GachaScript).where(GachaScript.id == gacha_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Gacha script not found")
    for field, value in req.model_dump().items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return GachaScriptOut(
        id=entry.id, title=entry.title, persona_id=entry.persona_id,
        storyline_json=entry.storyline_json, system_prompt_override=entry.system_prompt_override,
        gem_cost=entry.gem_cost, is_active=entry.is_active, created_by=entry.created_by,
        created_at=_to_utc_iso(entry.created_at),
    )


@router.delete("/gacha/{gacha_id}")
async def delete_gacha(
    gacha_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.gacha_script import GachaScript
    result = await db.execute(select(GachaScript).where(GachaScript.id == gacha_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Gacha script not found")
    await db.delete(entry)
    await db.commit()
    return {"message": "Deleted", "id": gacha_id}


# ── Virtual Gifts ──

@router.get("/gifts")
async def list_gifts(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.virtual_gift import VirtualGift
    result = await db.execute(select(VirtualGift).order_by(VirtualGift.sort_order, VirtualGift.id))
    return [
        GiftOut(
            id=g.id, name=g.name, icon_url=g.icon_url,
            energy_recovery=g.energy_recovery, gem_cost=g.gem_cost,
            category=g.category, is_active=g.is_active, sort_order=g.sort_order,
        )
        for g in result.scalars().all()
    ]


@router.post("/gifts")
async def create_gift(
    req: GiftCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.virtual_gift import VirtualGift
    entry = VirtualGift(**req.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return GiftOut(
        id=entry.id, name=entry.name, icon_url=entry.icon_url,
        energy_recovery=entry.energy_recovery, gem_cost=entry.gem_cost,
        category=entry.category, is_active=entry.is_active, sort_order=entry.sort_order,
    )


@router.put("/gifts/{gift_id}")
async def update_gift(
    gift_id: int,
    req: GiftCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.virtual_gift import VirtualGift
    result = await db.execute(select(VirtualGift).where(VirtualGift.id == gift_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Gift not found")
    for field, value in req.model_dump().items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return GiftOut(
        id=entry.id, name=entry.name, icon_url=entry.icon_url,
        energy_recovery=entry.energy_recovery, gem_cost=entry.gem_cost,
        category=entry.category, is_active=entry.is_active, sort_order=entry.sort_order,
    )


@router.delete("/gifts/{gift_id}")
async def delete_gift(
    gift_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.virtual_gift import VirtualGift
    result = await db.execute(select(VirtualGift).where(VirtualGift.id == gift_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Gift not found")
    await db.delete(entry)
    await db.commit()
    return {"message": "Deleted", "id": gift_id}


# ── Gem Transactions ──

@router.get("/transactions")
async def list_transactions(
    user_id: int | None = None,
    tx_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.gem_transaction import GemTransaction

    query = select(GemTransaction).order_by(GemTransaction.created_at.desc())
    count_q = select(func.count()).select_from(GemTransaction)
    if user_id:
        query = query.where(GemTransaction.user_id == user_id)
        count_q = count_q.where(GemTransaction.user_id == user_id)
    if tx_type:
        query = query.where(GemTransaction.tx_type == tx_type)
        count_q = count_q.where(GemTransaction.tx_type == tx_type)

    total = (await db.execute(count_q)).scalar() or 0
    result = await db.execute(query.offset(offset).limit(limit))
    txns = result.scalars().all()

    return {
        "transactions": [
            TransactionOut(
                id=t.id, user_id=t.user_id, amount=t.amount,
                balance_after=t.balance_after, tx_type=t.tx_type,
                reference_id=t.reference_id, description=t.description,
                created_at=_to_utc_iso(t.created_at),
            )
            for t in txns
        ],
        "total": total,
        "has_more": offset + limit < total,
    }


@router.get("/revenue/summary")
async def revenue_summary(
    days: int = 30,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.gem_transaction import GemTransaction
    from datetime import timedelta, timezone

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    total_spent_r = await db.execute(
        select(func.sum(GemTransaction.amount))
        .where(GemTransaction.amount < 0)
        .where(GemTransaction.created_at >= cutoff)
    )
    total_spent = abs(total_spent_r.scalar() or 0)

    total_earned_r = await db.execute(
        select(func.sum(GemTransaction.amount))
        .where(GemTransaction.amount > 0)
        .where(GemTransaction.created_at >= cutoff)
    )
    total_earned = total_earned_r.scalar() or 0

    tx_count_r = await db.execute(
        select(func.count(GemTransaction.id))
        .where(GemTransaction.created_at >= cutoff)
    )
    tx_count = tx_count_r.scalar() or 0

    return {
        "period_days": days,
        "total_gems_spent": total_spent,
        "total_gems_earned": total_earned,
        "transaction_count": tx_count,
    }


# ── CSV Export ──

@router.get("/transactions/export/csv")
async def export_transactions_csv(
    user_id: int | None = None,
    tx_type: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.gem_transaction import GemTransaction

    query = select(GemTransaction).order_by(GemTransaction.created_at.desc()).limit(5000)
    if user_id:
        query = query.where(GemTransaction.user_id == user_id)
    if tx_type:
        query = query.where(GemTransaction.tx_type == tx_type)

    result = await db.execute(query)
    txns = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "user_id", "amount", "balance_after", "tx_type", "reference_id", "description", "created_at"])
    for t in txns:
        writer.writerow([t.id, t.user_id, t.amount, t.balance_after, t.tx_type, t.reference_id, t.description, _to_utc_iso(t.created_at)])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions.csv"},
    )
