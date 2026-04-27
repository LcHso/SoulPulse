"""M4: Memory & Cognitive Management endpoints"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user, _to_utc_iso, audit_log

router = APIRouter(tags=["admin-memory"])


class MemoryOut(BaseModel):
    id: int
    user_id: int
    ai_id: int
    content: str
    memory_type: str
    vector_id: str
    created_at: str


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    memory_type: str | None = None


class AnchorOut(BaseModel):
    id: int
    user_id: int
    ai_id: int
    anchor_type: str
    content: str
    severity: int
    hit_count: int
    created_at: str


class KnowledgeEntryOut(BaseModel):
    id: int
    category: str
    content: str
    is_active: int
    created_by: int
    created_at: str


class KnowledgeCreate(BaseModel):
    category: str = "general"
    content: str
    is_active: int = 1


# ── Memory browsing (via admin_memory_service, NOT memory_service) ──

@router.get("/memories")
async def list_memories(
    user_id: int | None = None,
    ai_id: int | None = None,
    memory_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from services.admin_memory_service import list_memories as svc_list
    return await svc_list(db, user_id=user_id, ai_id=ai_id, memory_type=memory_type, limit=limit, offset=offset)


@router.get("/memories/{memory_id}")
async def get_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from services.admin_memory_service import get_memory as svc_get
    mem = await svc_get(db, memory_id)
    if not mem:
        raise HTTPException(status_code=404, detail="Memory not found")
    return mem


@router.put("/memories/{memory_id}")
async def update_memory(
    memory_id: int,
    req: MemoryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from services.admin_memory_service import update_memory as svc_update
    updated = await svc_update(db, memory_id, req.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found")
    return updated


@router.delete("/memories/{memory_id}")
@audit_log("delete_memory", "memory")
async def delete_memory(
    memory_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from services.admin_memory_service import delete_memory as svc_delete
    deleted = await svc_delete(db, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"message": "Memory deleted", "id": memory_id}


@router.get("/memories/search/semantic")
async def semantic_search(
    query: str,
    ai_id: int | None = None,
    user_id: int | None = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from services.admin_memory_service import semantic_search as svc_search
    return await svc_search(db, query=query, ai_id=ai_id, user_id=user_id, limit=limit)


# ── Relational Anchors ──

@router.get("/anchors")
async def list_anchors(
    user_id: int | None = None,
    ai_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.relational_anchor import RelationalAnchor

    query = select(RelationalAnchor).order_by(RelationalAnchor.created_at.desc())
    if user_id:
        query = query.where(RelationalAnchor.user_id == user_id)
    if ai_id:
        query = query.where(RelationalAnchor.ai_id == ai_id)

    result = await db.execute(query.offset(offset).limit(limit))
    anchors = result.scalars().all()
    return [
        AnchorOut(
            id=a.id, user_id=a.user_id, ai_id=a.ai_id,
            anchor_type=a.anchor_type, content=a.content,
            severity=a.severity, hit_count=a.hit_count,
            created_at=_to_utc_iso(a.created_at),
        )
        for a in anchors
    ]


@router.delete("/anchors/{anchor_id}")
async def delete_anchor(
    anchor_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.relational_anchor import RelationalAnchor
    result = await db.execute(select(RelationalAnchor).where(RelationalAnchor.id == anchor_id))
    anchor = result.scalar_one_or_none()
    if not anchor:
        raise HTTPException(status_code=404, detail="Anchor not found")
    await db.delete(anchor)
    await db.commit()
    return {"message": "Anchor deleted", "id": anchor_id}


# ── Global Knowledge Base ──

@router.get("/knowledge")
async def list_knowledge(
    category: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.global_knowledge_entry import GlobalKnowledgeEntry

    query = select(GlobalKnowledgeEntry).order_by(GlobalKnowledgeEntry.created_at.desc())
    if category:
        query = query.where(GlobalKnowledgeEntry.category == category)
    result = await db.execute(query.offset(offset).limit(limit))
    entries = result.scalars().all()
    return [
        KnowledgeEntryOut(
            id=e.id, category=e.category, content=e.content,
            is_active=e.is_active, created_by=e.created_by,
            created_at=_to_utc_iso(e.created_at),
        )
        for e in entries
    ]


@router.post("/knowledge")
async def create_knowledge(
    req: KnowledgeCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.global_knowledge_entry import GlobalKnowledgeEntry

    entry = GlobalKnowledgeEntry(
        category=req.category, content=req.content,
        is_active=req.is_active, created_by=admin.id,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return KnowledgeEntryOut(
        id=entry.id, category=entry.category, content=entry.content,
        is_active=entry.is_active, created_by=entry.created_by,
        created_at=_to_utc_iso(entry.created_at),
    )


@router.put("/knowledge/{entry_id}")
async def update_knowledge(
    entry_id: int,
    req: KnowledgeCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.global_knowledge_entry import GlobalKnowledgeEntry
    result = await db.execute(select(GlobalKnowledgeEntry).where(GlobalKnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    entry.category = req.category
    entry.content = req.content
    entry.is_active = req.is_active
    await db.commit()
    await db.refresh(entry)
    return KnowledgeEntryOut(
        id=entry.id, category=entry.category, content=entry.content,
        is_active=entry.is_active, created_by=entry.created_by,
        created_at=_to_utc_iso(entry.created_at),
    )


@router.delete("/knowledge/{entry_id}")
async def delete_knowledge(
    entry_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.global_knowledge_entry import GlobalKnowledgeEntry
    result = await db.execute(select(GlobalKnowledgeEntry).where(GlobalKnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Knowledge entry not found")
    await db.delete(entry)
    await db.commit()
    return {"message": "Deleted", "id": entry_id}
