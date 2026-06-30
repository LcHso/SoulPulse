"""M3: Persona & Soul Lab endpoints"""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from api.admin.dependencies import get_current_admin_user, _to_utc_iso

router = APIRouter(tags=["admin-persona"])

# 10 MB upload limit for character card files
MAX_CARD_FILE_SIZE = 10 * 1024 * 1024


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


@router.post("/personas/import-card")
async def import_persona_card(
    file: UploadFile = File(...),
    name_override: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin_user),
):
    """
    Import a SillyTavern character card (PNG or JSON) and create a global
    AIPersona (creator_user_id = NULL).

    - Accepts .png (with embedded card metadata) or .json card files.
    - Rejects files > 10MB (413).
    - When a PNG is uploaded, the image is also stored as the persona avatar
      under /static/avatars/imported/.
    - The created persona has creator_user_id = NULL (global / official).
    """
    from models.ai_persona import AIPersona
    from services.character_card_service import (
        character_card_service,
        extract_card_from_png,
    )
    from services.content_moderation_service import ContentModerationService

    moderation_service = ContentModerationService()

    content = await file.read()

    # ── File size check ──────────────────────────────────
    if len(content) > MAX_CARD_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum allowed size is 10MB.",
        )

    # ── Determine file type ─────────────────────────────────
    filename = (file.filename or "").lower()
    content_type = (file.content_type or "").lower()

    is_png = filename.endswith(".png") or content_type == "image/png"
    is_json = filename.endswith(".json") or content_type in (
        "application/json",
        "text/json",
    )

    if not is_png and not is_json:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Only .png and .json are accepted.",
        )

    # ── Parse card payload ─────────────────────────────────
    card: Optional[dict] = None
    if is_png:
        card = extract_card_from_png(content)
        if not card:
            raise HTTPException(
                status_code=400,
                detail="PNG does not contain a valid embedded character card.",
            )
    else:
        try:
            card = json.loads(content.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(
                status_code=400, detail="Invalid or unparseable JSON file."
            )

    if not isinstance(card, dict):
        raise HTTPException(
            status_code=400, detail="Malformed character card data."
        )

    # ── Validate required fields ─────────────────────────────────
    data_section = card.get("data") if isinstance(card.get("data"), dict) else {}
    card_name = (data_section.get("name") or card.get("name") or "").strip()
    if not card_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Character card is missing required field: name.",
        )

    # ── Map to persona fields ─────────────────────────────────
    persona_data = await character_card_service.import_card_to_persona_data(card)

    if name_override and name_override.strip():
        persona_data["name"] = name_override.strip()

    # personality_prompt is required (NOT NULL); ensure a non-empty value
    if not persona_data.get("personality_prompt"):
        persona_data["personality_prompt"] = (
            persona_data.get("bio") or persona_data["name"]
        )

    # ── Save PNG avatar (if applicable) ─────────────────────────────────
    avatar_url = ""
    if is_png:
        backend_dir = Path(__file__).resolve().parent.parent.parent
        avatar_dir = backend_dir / "static" / "avatars" / "imported"
        os.makedirs(avatar_dir, exist_ok=True)

        # Build a safe filename derived from the persona name + timestamp
        safe_name = re.sub(r"[^\w\-]+", "_", persona_data["name"]).strip("_") or "card"
        avatar_filename = f"{safe_name}_{int(time.time())}.png"
        avatar_path = avatar_dir / avatar_filename
        try:
            with open(avatar_path, "wb") as f:
                f.write(content)
        except OSError as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to save avatar: {e}"
            )

        avatar_url = f"/static/avatars/imported/{avatar_filename}"

    # ── Build AIPersona instance ─────────────────────────────────
    allowed_fields = {
        "name",
        "bio",
        "personality_prompt",
        "family_background",
        "tavern_card_json",
        "visual_prompt_tags",
        "secret_layers_json",
        "daily_routine_json",
        "voice_config_json",
        "category",
    }
    persona_kwargs = {
        k: v for k, v in persona_data.items() if k in allowed_fields and v is not None
    }
    # Global persona: creator_user_id is NULL
    persona_kwargs["creator_user_id"] = None
    persona_kwargs["persona_type"] = "imported"
    persona_kwargs["feature_tier"] = "full"
    persona_kwargs["is_public"] = False
    if avatar_url:
        persona_kwargs["avatar_url"] = avatar_url

    persona = AIPersona(**persona_kwargs)

    db.add(persona)
    try:
        await db.commit()
        await db.refresh(persona)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create persona: {e}"
        )

    # ── Audit log for admin imports ─────────────────────────────────────────
    # Admin-imported content is trusted (no rejection), but every import is
    # recorded so reviewers can audit who imported what and when.
    try:
        await moderation_service.log_moderation(
            db,
            content_type="admin_card_import",
            content_id=persona.id,
            user_id=0,
            ai_id=persona.id,
            action="approved",
            reason="admin_import",
        )
        await db.commit()
    except Exception:
        # Audit logging must never fail the admin import itself.
        await db.rollback()

    return {
        "status": "created",
        "message": "Character card imported and global persona created successfully.",
        "persona": {
            "id": persona.id,
            "name": persona.name,
            "bio": persona.bio,
            "profession": persona.profession,
            "gender_tag": persona.gender_tag,
            "category": persona.category,
            "archetype": persona.archetype,
            "base_face_url": persona.base_face_url,
            "visual_prompt_tags": persona.visual_prompt_tags,
            "avatar_url": persona.avatar_url,
            "is_active": persona.is_active,
            "personality_prompt": persona.personality_prompt,
            "family_background": persona.family_background,
            "creator_user_id": persona.creator_user_id,
            "tavern_card_json": persona.tavern_card_json,
        },
    }


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
