"""
Character Card API Endpoints

Provides import/export functionality for SillyTavern V2 character cards.

Endpoints:
- GET  /character-cards/{persona_id}/export      → Export persona as JSON card
- GET  /character-cards/{persona_id}/export-png  → Export persona as PNG card with embedded JSON
- POST /character-cards/import                    → Import card (PNG or JSON)
- POST /character-cards/import-and-create         → Import card and create user persona
- POST /character-cards/convert-markdown          → Convert SoulPulse markdown to V2 card
"""

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.security import get_current_user
from models.ai_persona import AIPersona
from models.emotion_state import EmotionState
from models.interaction import Interaction
from models.subscription import UserSubscription
from services.character_card_service import (
    character_card_service,
    convert_markdown_to_card,
    extract_card_from_png,
)
from services.content_moderation_service import ContentModerationService

# 10 MB upload limit for character card files
MAX_CARD_FILE_SIZE = 10 * 1024 * 1024

# Free tier import quota: non-subscribers can import up to this many characters
MAX_FREE_IMPORTS = 3

router = APIRouter(prefix="/character-cards", tags=["character-cards"])


@router.get("/{persona_id}/export")
async def export_character_card(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Export a persona as SillyTavern V2 JSON card."""
    result = await db.execute(select(AIPersona).where(AIPersona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    card = await character_card_service.export_persona_to_card(persona)
    return card


@router.get("/{persona_id}/export-png")
async def export_character_card_png(
    persona_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Export a persona as PNG character card (image with embedded JSON)."""
    result = await db.execute(select(AIPersona).where(AIPersona.id == persona_id))
    persona = result.scalar_one_or_none()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    if not persona.avatar_url:
        raise HTTPException(status_code=400, detail="Persona has no avatar image")

    # Resolve avatar path: support both /static/... URLs and absolute paths
    avatar_path = persona.avatar_url
    if avatar_path.startswith('/static/'):
        # Relative to backend/ directory
        backend_dir = Path(__file__).resolve().parent.parent.parent
        avatar_path = str(backend_dir / avatar_path.lstrip('/'))

    try:
        with open(avatar_path, 'rb') as f:
            avatar_bytes = f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Avatar file not found")

    png_card = await character_card_service.export_as_png_card(persona, avatar_bytes)

    return Response(
        content=png_card,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{persona.name}_card.png"'
        },
    )


@router.post("/import")
async def import_character_card(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Import a SillyTavern character card (PNG with embedded JSON or raw JSON file).
    Returns parsed card data and the persona field mappings ready for review/creation.
    """
    content = await file.read()

    card = None
    filename = (file.filename or "").lower()

    if filename.endswith('.png'):
        card = extract_card_from_png(content)
    elif filename.endswith('.json'):
        try:
            card = json.loads(content.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=400, detail="Invalid JSON file")
    else:
        # Try both formats
        card = extract_card_from_png(content)
        if not card:
            try:
                card = json.loads(content.decode('utf-8'))
            except Exception:
                card = None

    if not card:
        raise HTTPException(
            status_code=400,
            detail="Could not parse character card from file",
        )

    persona_data = await character_card_service.import_card_to_persona_data(card)

    return {
        "status": "parsed",
        "card": card,
        "persona_data": persona_data,
        "message": "Card parsed successfully. Use /personas endpoint to create the character.",
    }


@router.post("/import-and-create")
async def import_and_create_character(
    file: UploadFile = File(...),
    name_override: Optional[str] = Form(None),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Import a SillyTavern character card (PNG or JSON) and create a private
    AIPersona owned by the authenticated user.

    - Accepts .png (with embedded card metadata) or .json card files.
    - Rejects files > 10MB (413).
    - When a PNG is uploaded, the image is also stored as the persona avatar
      under /static/avatars/user_{user_id}/.
    - The created persona has creator_user_id = current_user.id (private).
    """
    content = await file.read()

    # ── File size check ──────────────────────────────────────────
    if len(content) > MAX_CARD_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large. Maximum allowed size is 10MB.",
        )

    # ── Determine file type ──────────────────────────────────────────
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

    # ── Parse card payload ──────────────────────────────────────────
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

    # ── Validate required fields ──────────────────────────────────────────
    data_section = card.get("data") if isinstance(card.get("data"), dict) else {}
    card_name = (data_section.get("name") or card.get("name") or "").strip()
    if not card_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Character card is missing required field: name.",
        )

    # ── Free tier import quota check ──────────────────────────────────────────
    import_count = await db.scalar(
        select(func.count(AIPersona.id)).where(
            AIPersona.creator_user_id == current_user.id
        )
    )

    active_sub = await db.scalar(
        select(UserSubscription).where(
            UserSubscription.user_id == current_user.id,
            UserSubscription.is_active == True,
            UserSubscription.expires_at > func.now(),
        )
    )

    if not active_sub and (import_count or 0) >= MAX_FREE_IMPORTS:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Free users can import up to {MAX_FREE_IMPORTS} characters. "
                "Subscribe to unlock unlimited imports."
            ),
        )

    # ── Map to persona fields ──────────────────────────────────────────
    persona_data = await character_card_service.import_card_to_persona_data(card)

    if name_override and name_override.strip():
        persona_data["name"] = name_override.strip()

    # personality_prompt is required (NOT NULL); ensure a non-empty value
    if not persona_data.get("personality_prompt"):
        persona_data["personality_prompt"] = (
            persona_data.get("bio") or persona_data["name"]
        )

    # ── Content moderation check ──────────────────────────────────────────
    # Scan the most descriptive free-text fields for clearly harmful content.
    # Imports flagged here are rejected with 422; passes are logged as approved
    # for admin audit (content_id is filled in after persona creation below).
    moderation_service = ContentModerationService()
    personality_text = (
        (persona_data.get("personality_prompt") or "")
        + " "
        + (persona_data.get("bio") or "")
    )
    is_safe, reason = await moderation_service.check_text(
        personality_text, current_user.id, db
    )
    if not is_safe:
        await moderation_service.log_moderation(
            db,
            content_type="character_card_import",
            content_id=0,
            user_id=current_user.id,
            ai_id=0,
            action="rejected",
            reason=reason,
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Character card content violates community guidelines: "
            + reason,
        )

    # ── Save PNG avatar (if applicable) ──────────────────────────────────────────
    avatar_url = ""
    if is_png:
        backend_dir = Path(__file__).resolve().parent.parent.parent
        avatar_dir = backend_dir / "static" / "avatars" / f"user_{current_user.id}"
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

        avatar_url = f"/static/avatars/user_{current_user.id}/{avatar_filename}"

    # ── Build AIPersona instance ──────────────────────────────────────────
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
    persona_kwargs["creator_user_id"] = current_user.id
    persona_kwargs["persona_type"] = "imported"
    persona_kwargs["feature_tier"] = "basic"
    persona_kwargs["is_public"] = False
    if avatar_url:
        persona_kwargs["avatar_url"] = avatar_url

    persona = AIPersona(**persona_kwargs)

    db.add(persona)
    try:
        # Flush to obtain the new persona ID without committing yet,
        # so we can attach EmotionState / Interaction records in the same transaction.
        await db.flush()

        # Create initial emotion state for this user-persona pair
        emotion_state = EmotionState(
            user_id=current_user.id,
            ai_id=persona.id,
            energy=0.7,
            pleasure=0.5,
            activation=0.5,
            longing=0.0,
            security=0.5,
        )
        db.add(emotion_state)

        # Create initial interaction record (intimacy starts at 0)
        interaction = Interaction(
            user_id=current_user.id,
            ai_id=persona.id,
            intimacy_score=0,
        )
        db.add(interaction)

        await db.commit()
        await db.refresh(persona)
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Failed to create persona: {e}"
        )

    # Log the approved import for audit trail (post-creation so we have id).
    try:
        await moderation_service.log_moderation(
            db,
            content_type="character_card_import",
            content_id=persona.id,
            user_id=current_user.id,
            ai_id=persona.id,
            action="approved",
            reason="automated_keyword_check_passed",
        )
        await db.commit()
    except Exception:
        # Audit logging must never fail the user-facing import.
        await db.rollback()

    return {
        "status": "created",
        "message": "Character card imported and persona created successfully.",
        "persona": {
            "id": persona.id,
            "name": persona.name,
            "bio": persona.bio,
            "avatar_url": persona.avatar_url,
        },
    }


@router.get("/import-quota")
async def get_import_quota(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's import quota status."""
    import_count = await db.scalar(
        select(func.count(AIPersona.id)).where(
            AIPersona.creator_user_id == current_user.id
        )
    )

    active_sub = await db.scalar(
        select(UserSubscription).where(
            UserSubscription.user_id == current_user.id,
            UserSubscription.is_active == True,
            UserSubscription.expires_at > func.now(),
        )
    )

    is_subscriber = active_sub is not None

    return {
        "used": import_count or 0,
        "limit": None if is_subscriber else MAX_FREE_IMPORTS,
        "is_subscriber": is_subscriber,
    }


@router.post("/convert-markdown")
async def convert_markdown_to_tavern(
    file: UploadFile = File(...),
):
    """Convert a SoulPulse character markdown file to SillyTavern V2 card format."""
    content = await file.read()

    # Write to temp file for parsing (parse_markdown_character expects a path)
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.md', delete=False, encoding='utf-8'
    ) as tmp:
        tmp.write(content.decode('utf-8'))
        tmp_path = tmp.name

    try:
        card = convert_markdown_to_card(tmp_path)
        return card
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse markdown: {str(e)}")
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
