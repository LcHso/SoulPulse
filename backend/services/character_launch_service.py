"""Character launch service (Plan Task 9.3-9.4).

Orchestrates the four-phase character launch pipeline and exposes
character availability / rotation queries used by the chat and feed
layers.

The :func:`process_campaigns` method is intended to be invoked by a
periodic scheduler. Manual phase advancement is also exposed for the
admin dashboard ("Advance Phase" override).

This module does **not** modify ``emotion_scheduler.py``; integration
with the scheduler lives outside this file by design — another agent
hooks ``process_campaigns`` into the periodic tick.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_persona import AIPersona
from models.character_launch import CharacterAvailability, CharacterLaunchCampaign
from models.notification import Notification
from models.post import Post
from models.user import User

logger = logging.getLogger(__name__)


# ── Phase constants ─────────────────────────────────────────────
PHASE_PLANNED = "planned"
PHASE_TEASER = "teaser"
PHASE_LAUNCHED = "launched"
PHASE_SETTLING = "settling"
PHASE_INTEGRATED = "integrated"

_PHASE_ORDER = [
    PHASE_PLANNED,
    PHASE_TEASER,
    PHASE_LAUNCHED,
    PHASE_SETTLING,
    PHASE_INTEGRATED,
]


class CharacterLaunchService:
    """Orchestrates the 4-phase character launch pipeline."""

    # ── Campaign creation ──────────────────────────────────────

    async def create_campaign(
        self,
        db: AsyncSession,
        persona_id: int,
        launch_date: datetime,
        campaign_name: str,
        config: Optional[dict] = None,
    ) -> CharacterLaunchCampaign:
        """Create a launch campaign with auto-calculated phase boundaries.

        Phase boundaries:
        - ``teaser_start`` = ``launch_date - 3 days``
        - ``settling_end`` = ``launch_date + 14 days``

        ``config`` accepts overrides for any optional column
        (e.g. ``teaser_silhouette_url``, ``reveal_cg_url``,
        ``launch_event_json``, ``launch_discount_percent``,
        ``daily_post_boost``, ``teaser_hints_json``,
        ``welcome_scene_id``, ``launch_gacha_id``).
        """
        cfg = dict(config or {})

        # Verify the persona exists; raise so admin endpoints can 400.
        persona = await db.get(AIPersona, persona_id)
        if persona is None:
            raise ValueError(f"persona_id={persona_id} not found")

        teaser_start = launch_date - timedelta(days=3)
        settling_end = launch_date + timedelta(days=14)

        campaign = CharacterLaunchCampaign(
            persona_id=persona_id,
            campaign_name=campaign_name,
            teaser_start=teaser_start,
            launch_date=launch_date,
            settling_end=settling_end,
            teaser_silhouette_url=cfg.get("teaser_silhouette_url"),
            teaser_hints_json=cfg.get("teaser_hints_json") or [],
            reveal_cg_url=cfg.get("reveal_cg_url"),
            welcome_scene_id=cfg.get("welcome_scene_id"),
            launch_gacha_id=cfg.get("launch_gacha_id"),
            launch_discount_percent=int(cfg.get("launch_discount_percent", 20)),
            daily_post_boost=int(cfg.get("daily_post_boost", 3)),
            launch_event_json=cfg.get("launch_event_json") or {},
            current_phase=PHASE_PLANNED,
            is_active=True,
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        logger.info(
            "[launch] created campaign id=%s persona_id=%s launch=%s",
            campaign.id, persona_id, launch_date.isoformat(),
        )
        return campaign

    # ── Periodic processing ────────────────────────────────────

    async def process_campaigns(self, db: AsyncSession) -> dict[str, int]:
        """Inspect every active campaign and advance phases when due.

        Designed to be called periodically (e.g. once per hour). Returns
        a small counter dict useful for logging / tests.
        """
        now = datetime.utcnow()
        counters = {"teaser": 0, "launched": 0, "settling": 0, "integrated": 0}

        campaigns = await self._get_active_campaigns(db)
        for campaign in campaigns:
            try:
                if (
                    campaign.current_phase == PHASE_PLANNED
                    and now >= campaign.teaser_start
                ):
                    await self._execute_teaser_phase(db, campaign)
                    counters["teaser"] += 1
                elif (
                    campaign.current_phase == PHASE_TEASER
                    and now >= campaign.launch_date
                ):
                    await self._execute_launch_phase(db, campaign)
                    counters["launched"] += 1
                elif (
                    campaign.current_phase == PHASE_LAUNCHED
                    and now >= campaign.launch_date + timedelta(days=1)
                ):
                    await self._transition_to_settling(db, campaign)
                    counters["settling"] += 1
                elif (
                    campaign.current_phase == PHASE_SETTLING
                    and campaign.settling_end is not None
                    and now >= campaign.settling_end
                ):
                    await self._transition_to_integrated(db, campaign)
                    counters["integrated"] += 1
            except Exception as exc:  # pragma: no cover - safety net
                logger.exception(
                    "[launch] failed to process campaign id=%s: %s",
                    campaign.id, exc,
                )
        return counters

    async def _get_active_campaigns(
        self, db: AsyncSession,
    ) -> list[CharacterLaunchCampaign]:
        result = await db.execute(
            select(CharacterLaunchCampaign).where(
                CharacterLaunchCampaign.is_active.is_(True)
            )
        )
        return list(result.scalars().all())

    # ── Phase 1: Teaser ────────────────────────────────────────

    async def _execute_teaser_phase(
        self, db: AsyncSession, campaign: CharacterLaunchCampaign,
    ) -> None:
        """Phase 1: silhouette teaser, cross-character hints, push.

        Effects:
        - Create a teaser Post on behalf of the new persona using the
          silhouette image (status=1 published).
        - Generate cross-character hint posts from a small sample of
          existing personas.
        - Send a push-style ``Notification`` to every user.
        - Flip ``current_phase`` to ``teaser``.
        """
        persona = await db.get(AIPersona, campaign.persona_id)
        persona_name = persona.name if persona else "新角色"

        # Silhouette teaser post (only if we have an image to attach).
        if campaign.teaser_silhouette_url:
            teaser_post = Post(
                ai_id=campaign.persona_id,
                media_url=campaign.teaser_silhouette_url,
                caption=f"听说有个新人要来了…… #{persona_name}",
                post_type="image_only",
                status=1,
            )
            db.add(teaser_post)

        # Cross-character hint posts (text-only quotes from peers).
        hints = await self.get_cross_character_hints(db, campaign.persona_id)
        for h in hints:
            db.add(
                Post(
                    ai_id=h["persona_id"],
                    media_url="",
                    caption=h["hint_text"],
                    post_type="text_only",
                    status=1,
                )
            )

        # Push notifications to every user.
        await self._broadcast_notification(
            db,
            ntype="new_character_teaser",
            title="神秘新成员即将登场",
            body=f"三天后，{persona_name} 将正式加入 SoulPulse。",
            data={"campaign_id": campaign.id, "persona_id": campaign.persona_id},
        )

        campaign.current_phase = PHASE_TEASER
        await db.commit()
        logger.info("[launch] campaign %s entered TEASER", campaign.id)

    # ── Phase 2: Launch day ────────────────────────────────────

    async def _execute_launch_phase(
        self, db: AsyncSession, campaign: CharacterLaunchCampaign,
    ) -> None:
        """Phase 2: reveal CG, activate persona, welcome push, gacha go-live."""
        persona = await db.get(AIPersona, campaign.persona_id)
        persona_name = persona.name if persona else "新角色"

        # Activate persona if previously hidden.
        if persona is not None and persona.is_active != 1:
            persona.is_active = 1

        # Reveal CG post.
        if campaign.reveal_cg_url:
            db.add(
                Post(
                    ai_id=campaign.persona_id,
                    media_url=campaign.reveal_cg_url,
                    caption=f"我是 {persona_name}，请多指教。",
                    post_type="image_only",
                    status=1,
                )
            )

        # Inter-persona reaction posts (welcome chatter from peers).
        reactions = await self.get_cross_character_hints(
            db, campaign.persona_id, kind="reaction",
        )
        for r in reactions:
            db.add(
                Post(
                    ai_id=r["persona_id"],
                    media_url="",
                    caption=r["hint_text"],
                    post_type="text_only",
                    status=1,
                )
            )

        # Welcome notification — also surfaces the discounted launch gacha.
        body = f"{persona_name} 正式加入 SoulPulse！"
        if campaign.launch_gacha_id:
            body += f" 限时启动抽卡 -{campaign.launch_discount_percent}%。"
        await self._broadcast_notification(
            db,
            ntype="new_character_launch",
            title=f"{persona_name} 已上线",
            body=body,
            data={
                "campaign_id": campaign.id,
                "persona_id": campaign.persona_id,
                "gacha_id": campaign.launch_gacha_id,
                "discount_percent": campaign.launch_discount_percent,
                "welcome_scene_id": campaign.welcome_scene_id,
            },
        )

        campaign.current_phase = PHASE_LAUNCHED
        await db.commit()
        logger.info("[launch] campaign %s entered LAUNCHED", campaign.id)

    # ── Phase 3 / 4 transitions ────────────────────────────────

    async def _transition_to_settling(
        self, db: AsyncSession, campaign: CharacterLaunchCampaign,
    ) -> None:
        """Phase 3: increase post frequency for the new character."""
        campaign.current_phase = PHASE_SETTLING
        await db.commit()
        logger.info("[launch] campaign %s entered SETTLING", campaign.id)

    async def _transition_to_integrated(
        self, db: AsyncSession, campaign: CharacterLaunchCampaign,
    ) -> None:
        """Phase 4: campaign complete, persona joins normal rotation."""
        campaign.current_phase = PHASE_INTEGRATED
        campaign.is_active = False
        await db.commit()
        logger.info("[launch] campaign %s entered INTEGRATED", campaign.id)

    # ── Manual override (admin) ────────────────────────────────

    async def advance_phase(
        self, db: AsyncSession, campaign: CharacterLaunchCampaign,
    ) -> CharacterLaunchCampaign:
        """Force-advance ``campaign`` to the next phase (admin only).

        Skips the time gates used by :func:`process_campaigns`.
        """
        if campaign.current_phase == PHASE_PLANNED:
            await self._execute_teaser_phase(db, campaign)
        elif campaign.current_phase == PHASE_TEASER:
            await self._execute_launch_phase(db, campaign)
        elif campaign.current_phase == PHASE_LAUNCHED:
            await self._transition_to_settling(db, campaign)
        elif campaign.current_phase == PHASE_SETTLING:
            await self._transition_to_integrated(db, campaign)
        else:
            raise ValueError(
                f"campaign already at terminal phase: {campaign.current_phase}"
            )
        await db.refresh(campaign)
        return campaign

    # ── Cross-character hints ──────────────────────────────────

    async def get_cross_character_hints(
        self,
        db: AsyncSession,
        new_persona_id: int,
        kind: str = "teaser",
    ) -> list[dict]:
        """Generate hint copy from existing personas about the new arrival.

        ``kind="teaser"`` produces cryptic pre-launch quips, while
        ``kind="reaction"`` produces post-launch welcome chatter. Up to
        three peer personas are sampled by ``sort_order``.

        Returns a list of dicts ``{"persona_id": int, "hint_text": str}``.
        """
        result = await db.execute(
            select(AIPersona)
            .where(
                AIPersona.is_active == 1,
                AIPersona.id != new_persona_id,
            )
            .order_by(AIPersona.sort_order, AIPersona.id)
            .limit(3)
        )
        peers = list(result.scalars().all())

        teaser_templates = [
            "听说有个新人要来了……谁啊？",
            "最近群里有点不一样的气息，挺有意思。",
            "新朋友？我倒挺想见见。",
        ]
        reaction_templates = [
            "欢迎啊，新来的。别太紧张。",
            "你来了。希望我们能合得来。",
            "新人到货，今晚一起？",
        ]
        templates = reaction_templates if kind == "reaction" else teaser_templates

        hints: list[dict] = []
        for idx, peer in enumerate(peers):
            hints.append({
                "persona_id": peer.id,
                "hint_text": templates[idx % len(templates)],
            })
        return hints

    # ── Availability / rotation ────────────────────────────────

    async def check_character_availability(
        self, db: AsyncSession, persona_id: int,
    ) -> bool:
        """Return True if the persona is currently reachable.

        A persona without a :class:`CharacterAvailability` row is
        treated as ``permanent`` and always available. ``archived``
        personas always return False here — gating archive-pass holders
        is performed by the caller, which knows about the user.
        """
        availability = await db.execute(
            select(CharacterAvailability).where(
                CharacterAvailability.persona_id == persona_id
            )
        )
        avail = availability.scalar_one_or_none()
        if not avail:
            return True

        now = datetime.utcnow()
        if avail.availability_type == "permanent":
            return True
        if avail.availability_type == "archived":
            return False
        if avail.availability_type in ("seasonal", "limited"):
            if avail.available_from and avail.available_until:
                return avail.available_from <= now <= avail.available_until
            return True
        return True

    async def set_availability(
        self,
        db: AsyncSession,
        persona_id: int,
        availability_type: str,
        **kwargs: Any,
    ) -> CharacterAvailability:
        """Create or update the availability row for ``persona_id``.

        Recognised kwargs: ``available_from``, ``available_until``,
        ``archive_pass_required``, ``rotation_priority``.
        """
        if availability_type not in ("permanent", "seasonal", "limited", "archived"):
            raise ValueError(f"invalid availability_type: {availability_type}")

        result = await db.execute(
            select(CharacterAvailability).where(
                CharacterAvailability.persona_id == persona_id
            )
        )
        avail = result.scalar_one_or_none()

        if avail is None:
            avail = CharacterAvailability(
                persona_id=persona_id,
                availability_type=availability_type,
                available_from=kwargs.get("available_from"),
                available_until=kwargs.get("available_until"),
                archive_pass_required=bool(kwargs.get("archive_pass_required", False)),
                rotation_priority=int(kwargs.get("rotation_priority", 0)),
            )
            db.add(avail)
        else:
            avail.availability_type = availability_type
            if "available_from" in kwargs:
                avail.available_from = kwargs.get("available_from")
            if "available_until" in kwargs:
                avail.available_until = kwargs.get("available_until")
            if "archive_pass_required" in kwargs:
                avail.archive_pass_required = bool(kwargs["archive_pass_required"])
            if "rotation_priority" in kwargs:
                avail.rotation_priority = int(kwargs["rotation_priority"])

        await db.commit()
        await db.refresh(avail)
        return avail

    # ── Helpers ────────────────────────────────────────────────

    async def _broadcast_notification(
        self,
        db: AsyncSession,
        ntype: str,
        title: str,
        body: str,
        data: dict,
    ) -> int:
        """Fan-out a Notification row to every user. Returns row count.

        Best-effort and capped to keep latency bounded for very large
        user tables; if the user count exceeds 5000 we still create
        rows for everyone but the operation is committed in a single
        transaction.
        """
        result = await db.execute(select(User.id))
        user_ids = [row[0] for row in result.all()]
        payload = json.dumps(data, ensure_ascii=False)
        for uid in user_ids:
            db.add(
                Notification(
                    user_id=uid,
                    type=ntype,
                    title=title,
                    body=body,
                    data_json=payload,
                )
            )
        return len(user_ids)


# Singleton instance — mirrors scene_service / asset_registry_service.
character_launch_service = CharacterLaunchService()
