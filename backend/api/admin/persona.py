"""M3: Persona & Soul Lab endpoints"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user, _to_utc_iso

router = APIRouter(tags=["admin-persona"])


class PersonaOut(BaseModel):
    id: int
    name: str
    bio: str
    profession: str
    gender_tag: str
    category: str
    archetype: str
    base_face_url: str | None
    visual_prompt_tags: str | None
    avatar_url: str
    is_active: int
    personality_prompt: str


class PersonaUpdateRequest(BaseModel):
    visual_prompt_tags: str | None = None
    base_face_url: str | None = None
    avatar_url: str | None = None
    is_active: int | None = None
    bio: str | None = None
    personality_prompt: str | None = None
    name: str | None = None
    profession: str | None = None
    archetype: str | None = None
    ins_style_tags: str | None = None


class EmotionStateOut(BaseModel):
    id: int
    user_id: int
    ai_id: int
    energy: float
    pleasure: float
    activation: float
    longing: float
    security: float
    updated_at: str


class EmotionUpdateRequest(BaseModel):
    energy: float | None = None
    pleasure: float | None = None
    activation: float | None = None
    longing: float | None = None
    security: float | None = None


class MilestoneOut(BaseModel):
    id: int
    persona_id: int
    intimacy_level: int
    level_name: str
    min_score: int
    unlock_features_json: str
    trigger_message: str


class MilestoneCreate(BaseModel):
    persona_id: int
    intimacy_level: int
    level_name: str = ""
    min_score: int = 0
    unlock_features_json: str = "[]"
    trigger_message: str = ""


# ── Persona CRUD (migrated + extended) ──

@router.get("/personas")
async def list_personas(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.ai_persona import AIPersona
    result = await db.execute(select(AIPersona).order_by(AIPersona.sort_order, AIPersona.id))
    personas = result.scalars().all()
    return [
        PersonaOut(
            id=p.id, name=p.name, bio=p.bio, profession=p.profession,
            gender_tag=p.gender_tag, category=p.category, archetype=p.archetype,
            base_face_url=p.base_face_url, visual_prompt_tags=p.visual_prompt_tags,
            avatar_url=p.avatar_url, is_active=p.is_active,
            personality_prompt=p.personality_prompt,
        )
        for p in personas
    ]


@router.get("/personas/{persona_id}")
async def get_persona(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.ai_persona import AIPersona
    result = await db.execute(select(AIPersona).where(AIPersona.id == persona_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Persona not found")
    return PersonaOut(
        id=p.id, name=p.name, bio=p.bio, profession=p.profession,
        gender_tag=p.gender_tag, category=p.category, archetype=p.archetype,
        base_face_url=p.base_face_url, visual_prompt_tags=p.visual_prompt_tags,
        avatar_url=p.avatar_url, is_active=p.is_active,
        personality_prompt=p.personality_prompt,
    )


@router.put("/personas/{persona_id}")
async def update_persona(
    persona_id: int,
    request: PersonaUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.ai_persona import AIPersona
    result = await db.execute(select(AIPersona).where(AIPersona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    for field, value in request.model_dump(exclude_none=True).items():
        setattr(persona, field, value)

    await db.commit()
    await db.refresh(persona)
    return PersonaOut(
        id=persona.id, name=persona.name, bio=persona.bio, profession=persona.profession,
        gender_tag=persona.gender_tag, category=persona.category, archetype=persona.archetype,
        base_face_url=persona.base_face_url, visual_prompt_tags=persona.visual_prompt_tags,
        avatar_url=persona.avatar_url, is_active=persona.is_active,
        personality_prompt=persona.personality_prompt,
    )


# ── Prompt preview (via admin_sandbox_service, NOT chat_service) ──

class PromptPreviewRequest(BaseModel):
    persona_id: int
    user_message: str
    system_prompt_override: str | None = None


@router.post("/personas/prompt-preview")
async def prompt_preview(
    req: PromptPreviewRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.ai_persona import AIPersona
    from services.admin_sandbox_service import sandbox_chat

    result = await db.execute(select(AIPersona).where(AIPersona.id == req.persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    system_prompt = req.system_prompt_override or persona.personality_prompt
    reply = await sandbox_chat(system_prompt=system_prompt, user_message=req.user_message)
    return {"reply": reply, "system_prompt_used": system_prompt}


# ── Emotion view/edit (via admin_emotion_service, NOT emotion_engine) ──

@router.get("/emotions/{persona_id}")
async def list_emotion_states(
    persona_id: int,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from services.admin_emotion_service import get_emotion_states
    return await get_emotion_states(db, persona_id, limit)


@router.get("/emotions/{persona_id}/user/{user_id}")
async def get_user_emotion(
    persona_id: int,
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from services.admin_emotion_service import get_emotion_state
    state = await get_emotion_state(db, user_id, persona_id)
    if not state:
        raise HTTPException(status_code=404, detail="Emotion state not found")
    return state


@router.put("/emotions/{persona_id}/user/{user_id}")
async def update_emotion(
    persona_id: int,
    user_id: int,
    req: EmotionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from services.admin_emotion_service import update_emotion_state
    updated = await update_emotion_state(db, user_id, persona_id, req.model_dump(exclude_none=True))
    if not updated:
        raise HTTPException(status_code=404, detail="Emotion state not found")
    return updated


# ── Milestone config ──

@router.get("/milestones/{persona_id}")
async def list_milestones(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.milestone_config import MilestoneConfig
    result = await db.execute(
        select(MilestoneConfig)
        .where(MilestoneConfig.persona_id == persona_id)
        .order_by(MilestoneConfig.intimacy_level)
    )
    return [
        MilestoneOut(
            id=m.id, persona_id=m.persona_id, intimacy_level=m.intimacy_level,
            level_name=m.level_name, min_score=m.min_score,
            unlock_features_json=m.unlock_features_json, trigger_message=m.trigger_message,
        )
        for m in result.scalars().all()
    ]


@router.post("/milestones")
async def create_milestone(
    req: MilestoneCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.milestone_config import MilestoneConfig
    entry = MilestoneConfig(**req.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return MilestoneOut(
        id=entry.id, persona_id=entry.persona_id, intimacy_level=entry.intimacy_level,
        level_name=entry.level_name, min_score=entry.min_score,
        unlock_features_json=entry.unlock_features_json, trigger_message=entry.trigger_message,
    )


@router.put("/milestones/{milestone_id}")
async def update_milestone(
    milestone_id: int,
    req: MilestoneCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.milestone_config import MilestoneConfig
    result = await db.execute(select(MilestoneConfig).where(MilestoneConfig.id == milestone_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Milestone not found")
    for field, value in req.model_dump().items():
        setattr(entry, field, value)
    await db.commit()
    await db.refresh(entry)
    return MilestoneOut(
        id=entry.id, persona_id=entry.persona_id, intimacy_level=entry.intimacy_level,
        level_name=entry.level_name, min_score=entry.min_score,
        unlock_features_json=entry.unlock_features_json, trigger_message=entry.trigger_message,
    )


@router.delete("/milestones/{milestone_id}")
async def delete_milestone(
    milestone_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    from models.milestone_config import MilestoneConfig
    result = await db.execute(select(MilestoneConfig).where(MilestoneConfig.id == milestone_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Milestone not found")
    await db.delete(entry)
    await db.commit()
    return {"message": "Deleted", "id": milestone_id}
