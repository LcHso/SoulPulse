"""Scene service for managing conversation scenes and interactive narratives.

Implements Plan Task 3 backend logic:
- Scene discovery (list available scenes for a user/persona).
- Scene lifecycle: start -> record_message (auto-complete) -> complete/abandon.
- Active scene context lookup for prompt injection by chat_service (the
  integration is performed by another agent; this service exposes the API).
- Interactive choice points: parse [CHOICE_X: ...] markers from AI replies
  and persist the user's selection in UserSceneProgress.choices_made_json.

The service is a singleton (``scene_service`` at module level), mirroring
``asset_registry_service`` and ``milestone_service`` patterns used elsewhere
in this project.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.chat_scene import ChatScene, UserSceneProgress
from models.interaction import Interaction

logger = logging.getLogger(__name__)


# Marker pattern: [CHOICE_A: text | CHOICE_B: text | CHOICE_C: text]
# We extract the inner block first, then iterate over each "CHOICE_<KEY>: text" pair.
_CHOICE_BLOCK_RE = re.compile(r"\[(CHOICE_[A-Z]:\s*[^\]]+)\]")
_CHOICE_PAIR_RE = re.compile(r"CHOICE_([A-Z])\s*:\s*([^|\]]+)")


class SceneService:
    """Manages scene lifecycle: start, progress, completion, rewards."""

    # ── Discovery ──────────────────────────────────────────────

    async def get_available_scenes(
        self,
        db: AsyncSession,
        persona_id: int,
        user_id: int,
        intimacy_score: float,
    ) -> list[dict]:
        """Return scenes available to ``user_id`` for ``persona_id``.

        A scene is considered available when:
        - ``is_active`` is True
        - ``required_intimacy`` <= the user's current intimacy score
        - ``unlock_type == "free"`` OR the user has previously
          completed/started the scene (cached in UserSceneProgress)

        The result is annotated with the user's progress state so the UI
        can mark scenes as locked / completed / in_progress.
        """
        scenes_q = (
            select(ChatScene)
            .where(
                ChatScene.persona_id == persona_id,
                ChatScene.is_active.is_(True),
            )
            .order_by(ChatScene.sort_order, ChatScene.id)
        )
        scenes = list((await db.execute(scenes_q)).scalars().all())
        if not scenes:
            return []

        # Map scene_id -> latest progress for this user
        progress_q = select(UserSceneProgress).where(
            UserSceneProgress.user_id == user_id,
            UserSceneProgress.persona_id == persona_id,
            UserSceneProgress.scene_id.in_([s.id for s in scenes]),
        )
        progress_rows = list((await db.execute(progress_q)).scalars().all())
        latest_progress: dict[int, UserSceneProgress] = {}
        for row in progress_rows:
            existing = latest_progress.get(row.scene_id)
            if existing is None or (row.id or 0) > (existing.id or 0):
                latest_progress[row.scene_id] = row

        out: list[dict] = []
        for s in scenes:
            prog = latest_progress.get(s.id)
            unlocked = (
                s.unlock_type == "free"
                or (prog is not None and prog.status == "completed")
                or (prog is not None and prog.status == "in_progress")
            )
            available = unlocked and intimacy_score >= float(s.required_intimacy)
            out.append(
                {
                    "id": s.id,
                    "scene_name": s.scene_name,
                    "scene_type": s.scene_type,
                    "setting_description": s.setting_description,
                    "mood_preset": s.mood_preset,
                    "required_intimacy": s.required_intimacy,
                    "unlock_type": s.unlock_type,
                    "unlock_cost": s.unlock_cost,
                    "max_messages": s.max_messages,
                    "scene_cg_url": s.scene_cg_url,
                    "sort_order": s.sort_order,
                    "available": available,
                    "locked_reason": (
                        None
                        if available
                        else (
                            "intimacy_too_low"
                            if intimacy_score < float(s.required_intimacy)
                            else "unlock_required"
                        )
                    ),
                    "user_status": prog.status if prog else None,
                }
            )
        return out

    # ── Lifecycle ──────────────────────────────────────────────

    async def start_scene(
        self,
        db: AsyncSession,
        user_id: int,
        persona_id: int,
        scene_id: int,
    ) -> dict:
        """Start a new scene session.

        - Validates user can access the scene (intimacy / unlock).
        - Creates a fresh UserSceneProgress row.
        - Sets ``Interaction.active_scene_id`` for the (user, persona) pair.
        - Returns scene context that callers can inject into chat prompts.
        """
        scene = await self._load_scene(db, scene_id)
        if not scene or not scene.is_active:
            raise ValueError("Scene not found or inactive")
        if scene.persona_id != persona_id:
            raise ValueError("Scene does not belong to this persona")

        interaction = await self._get_or_create_interaction(db, user_id, persona_id)

        if float(interaction.intimacy_score) < float(scene.required_intimacy):
            raise ValueError("Intimacy too low for this scene")

        # Free scenes start immediately. Paid/gacha/milestone unlocks are
        # assumed to be checked upstream (commerce flow), but we still
        # require any prior completion record for non-free scenes if the
        # user hasn't paid through this flow.
        if scene.unlock_type != "free":
            prior_q = select(UserSceneProgress).where(
                UserSceneProgress.user_id == user_id,
                UserSceneProgress.scene_id == scene.id,
            )
            prior = (await db.execute(prior_q)).scalars().first()
            if prior is None:
                # No prior unlock — caller must perform purchase/unlock first.
                raise ValueError(
                    f"Scene requires {scene.unlock_type} unlock before it can be started"
                )

        progress = UserSceneProgress(
            user_id=user_id,
            scene_id=scene.id,
            persona_id=persona_id,
            status="in_progress",
            messages_count=0,
            choices_made_json=[],
        )
        db.add(progress)
        await db.flush()

        interaction.active_scene_id = scene.id
        await db.commit()
        await db.refresh(progress)

        return {
            "progress_id": progress.id,
            "scene_id": scene.id,
            "scene_name": scene.scene_name,
            "scene_type": scene.scene_type,
            "setting_description": scene.setting_description,
            "mood_preset": scene.mood_preset,
            "system_prompt_addon": scene.system_prompt_addon,
            "scene_cg_url": scene.scene_cg_url,
            "max_messages": scene.max_messages,
            "messages_remaining": scene.max_messages,
        }

    async def get_active_scene_context(
        self,
        db: AsyncSession,
        user_id: int,
        persona_id: int,
    ) -> Optional[dict]:
        """Return the active scene context for prompt injection, or None.

        If the active scene has reached ``max_messages``, this method
        auto-completes the scene and returns ``None`` for subsequent calls.
        """
        interaction = await self._get_interaction(db, user_id, persona_id)
        if interaction is None or interaction.active_scene_id is None:
            return None

        scene = await self._load_scene(db, interaction.active_scene_id)
        if scene is None:
            # Dangling reference — clear it.
            interaction.active_scene_id = None
            await db.commit()
            return None

        progress = await self._get_active_progress(db, user_id, scene.id)
        if progress is None:
            interaction.active_scene_id = None
            await db.commit()
            return None

        if progress.messages_count >= scene.max_messages:
            # Auto-complete the scene.
            await self.complete_scene(db, user_id, persona_id, scene.id)
            return None

        return {
            "scene_id": scene.id,
            "scene_name": scene.scene_name,
            "scene_type": scene.scene_type,
            "setting_description": scene.setting_description,
            "mood_preset": scene.mood_preset,
            "system_prompt_addon": scene.system_prompt_addon,
            "scene_cg_url": scene.scene_cg_url,
            "max_messages": scene.max_messages,
            "messages_count": progress.messages_count,
            "messages_remaining": max(0, scene.max_messages - progress.messages_count),
        }

    async def record_message(
        self,
        db: AsyncSession,
        user_id: int,
        persona_id: int,
    ) -> Optional[dict]:
        """Increment the message counter for the active scene.

        Returns a completion summary dict if the scene reached its
        ``max_messages`` cap (and was therefore auto-completed), otherwise
        ``None``.
        """
        interaction = await self._get_interaction(db, user_id, persona_id)
        if interaction is None or interaction.active_scene_id is None:
            return None

        scene = await self._load_scene(db, interaction.active_scene_id)
        if scene is None:
            interaction.active_scene_id = None
            await db.commit()
            return None

        progress = await self._get_active_progress(db, user_id, scene.id)
        if progress is None:
            interaction.active_scene_id = None
            await db.commit()
            return None

        progress.messages_count += 1
        await db.commit()

        if progress.messages_count >= scene.max_messages:
            return await self.complete_scene(db, user_id, persona_id, scene.id)

        return None

    async def complete_scene(
        self,
        db: AsyncSession,
        user_id: int,
        persona_id: int,
        scene_id: int,
    ) -> dict:
        """Complete a scene session and apply rewards.

        - Marks UserSceneProgress.status = "completed".
        - Clears ``Interaction.active_scene_id``.
        - Applies intimacy bonus (if any) directly on the Interaction.
        - Returns a summary including the reward payload so the caller
          can surface achievement / CG unlock notifications to the user.
        """
        scene = await self._load_scene(db, scene_id)
        if scene is None:
            raise ValueError("Scene not found")

        progress = await self._get_active_progress(db, user_id, scene_id)
        if progress is None:
            # Already completed or never started — be tolerant and return
            # a no-op result so chat_service can still clear UI state.
            interaction = await self._get_interaction(db, user_id, persona_id)
            if interaction is not None and interaction.active_scene_id == scene_id:
                interaction.active_scene_id = None
                await db.commit()
            return {
                "scene_id": scene_id,
                "status": "already_completed",
                "rewards": {},
            }

        progress.status = "completed"
        progress.completed_at = datetime.now(timezone.utc)

        rewards = scene.completion_reward_json or {}
        interaction = await self._get_or_create_interaction(db, user_id, persona_id)

        intimacy_bonus = float(rewards.get("intimacy_bonus", 0) or 0)
        if intimacy_bonus:
            interaction.intimacy_score = min(
                100.0, float(interaction.intimacy_score) + intimacy_bonus
            )

        interaction.active_scene_id = None
        await db.commit()

        return {
            "scene_id": scene_id,
            "scene_name": scene.scene_name,
            "status": "completed",
            "messages_count": progress.messages_count,
            "rewards": rewards,
            "intimacy_after": float(interaction.intimacy_score),
        }

    async def abandon_scene(
        self,
        db: AsyncSession,
        user_id: int,
        persona_id: int,
    ) -> None:
        """User exits a scene early. Marks current progress as abandoned."""
        interaction = await self._get_interaction(db, user_id, persona_id)
        if interaction is None or interaction.active_scene_id is None:
            return

        progress = await self._get_active_progress(
            db, user_id, interaction.active_scene_id
        )
        if progress is not None:
            progress.status = "abandoned"
            progress.completed_at = datetime.now(timezone.utc)

        interaction.active_scene_id = None
        await db.commit()

    # ── Interactive choices ─────────────────────────────────────

    async def parse_choices(self, ai_response: str) -> Optional[list[dict]]:
        """Parse interactive choice points from an AI reply.

        Recognises the inline marker format::

            [CHOICE_A: 拥抱他 | CHOICE_B: 轻轻拍他的头 | CHOICE_C: 沉默地看着他]

        Returns a list like ``[{"key": "A", "text": "拥抱他"}, ...]`` or
        ``None`` when no choice block is present.
        """
        if not ai_response:
            return None
        block_match = _CHOICE_BLOCK_RE.search(ai_response)
        if not block_match:
            return None

        block = block_match.group(1)
        choices: list[dict] = []
        for key, text in _CHOICE_PAIR_RE.findall(block):
            cleaned = text.strip().rstrip("|").strip()
            if cleaned:
                choices.append({"key": key, "text": cleaned})

        return choices or None

    async def record_choice(
        self,
        db: AsyncSession,
        user_id: int,
        persona_id: int,
        choice_key: str,
    ) -> None:
        """Append the user's choice to the active scene's progress record."""
        interaction = await self._get_interaction(db, user_id, persona_id)
        if interaction is None or interaction.active_scene_id is None:
            raise ValueError("No active scene to record choice for")

        progress = await self._get_active_progress(
            db, user_id, interaction.active_scene_id
        )
        if progress is None:
            raise ValueError("No active scene progress found")

        choices: list[Any] = list(progress.choices_made_json or [])
        choices.append(
            {
                "key": choice_key,
                "at": datetime.now(timezone.utc).isoformat(),
                "message_index": progress.messages_count,
            }
        )
        # Reassign so SQLAlchemy detects the JSON change.
        progress.choices_made_json = choices
        await db.commit()

    # ── Internal helpers ────────────────────────────────────────

    async def _load_scene(
        self, db: AsyncSession, scene_id: int
    ) -> Optional[ChatScene]:
        result = await db.execute(select(ChatScene).where(ChatScene.id == scene_id))
        return result.scalar_one_or_none()

    async def _get_interaction(
        self, db: AsyncSession, user_id: int, persona_id: int
    ) -> Optional[Interaction]:
        result = await db.execute(
            select(Interaction).where(
                Interaction.user_id == user_id,
                Interaction.ai_id == persona_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_or_create_interaction(
        self, db: AsyncSession, user_id: int, persona_id: int
    ) -> Interaction:
        interaction = await self._get_interaction(db, user_id, persona_id)
        if interaction is not None:
            return interaction
        interaction = Interaction(user_id=user_id, ai_id=persona_id)
        db.add(interaction)
        await db.flush()
        return interaction

    async def _get_active_progress(
        self, db: AsyncSession, user_id: int, scene_id: int
    ) -> Optional[UserSceneProgress]:
        result = await db.execute(
            select(UserSceneProgress)
            .where(
                UserSceneProgress.user_id == user_id,
                UserSceneProgress.scene_id == scene_id,
                UserSceneProgress.status == "in_progress",
            )
            .order_by(UserSceneProgress.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


# Module-level singleton, mirroring asset_registry_service / milestone_service.
scene_service = SceneService()
