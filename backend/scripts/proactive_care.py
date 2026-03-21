"""Proactive care scheduler.  *** DEPRECATED ***

This scheduler has been superseded by scripts/emotion_scheduler.py, which
subsumes the memory-care DM logic as one of several emotion-driven proactive
triggers.  Kept here for reference only — run emotion_scheduler.py instead.

Original behaviour:
  Runs every 24 hours. For each user with intimacy > 7, scans long-term
  memories for schedule-related events (exams, meetings, trips, etc.)
  and generates a caring DM from the AI companion.

Run from the backend directory:
    python3 scripts/proactive_care.py
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import init_db, async_session
from models.user import User  # noqa: F401 — FK resolution
from models.interaction import Interaction
from models.ai_persona import AIPersona
from models.proactive_dm import ProactiveDM
from services.milestone_service import generate_proactive_message

INTIMACY_THRESHOLD = 7.0
CHECK_INTERVAL = 86400  # 24 hours in seconds


async def check_and_send_proactive_dms():
    """Scan high-intimacy users and send proactive care DMs."""
    print(f"[proactive] Starting scan at {datetime.now(timezone.utc).isoformat()}")

    async with async_session() as db:
        # Find all interactions with intimacy > threshold
        result = await db.execute(
            select(Interaction).where(
                Interaction.intimacy_score > INTIMACY_THRESHOLD
            )
        )
        interactions = result.scalars().all()

        if not interactions:
            print("[proactive] No high-intimacy users found, skipping.")
            return

        print(f"[proactive] Found {len(interactions)} high-intimacy interactions")

        # Load all AI personas for lookup
        persona_result = await db.execute(select(AIPersona))
        personas = {p.id: p for p in persona_result.scalars().all()}

        sent_count = 0
        for interaction in interactions:
            persona = personas.get(interaction.ai_id)
            if not persona:
                continue

            print(
                f"[proactive] Checking user_id={interaction.user_id} "
                f"ai_id={interaction.ai_id} "
                f"intimacy={interaction.intimacy_score:.1f}"
            )

            # Check if we already sent a DM today
            from sqlalchemy import func as sqlfunc
            today_check = await db.execute(
                select(sqlfunc.count(ProactiveDM.id)).where(
                    ProactiveDM.user_id == interaction.user_id,
                    ProactiveDM.ai_id == interaction.ai_id,
                    ProactiveDM.created_at >= datetime.now(timezone.utc).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    ),
                )
            )
            already_sent = today_check.scalar() or 0
            if already_sent > 0:
                print(f"  Already sent today, skipping.")
                continue

            # Generate proactive message from memories
            result = await generate_proactive_message(
                user_id=interaction.user_id,
                ai_id=interaction.ai_id,
                persona_prompt=persona.personality_prompt,
            )

            if result is None:
                print(f"  No relevant events found, skipping.")
                continue

            # Store the proactive DM
            dm = ProactiveDM(
                user_id=interaction.user_id,
                ai_id=interaction.ai_id,
                event=result["event"],
                message=result["message"],
            )
            db.add(dm)
            await db.commit()
            sent_count += 1

            print(
                f"  Sent proactive DM: [{result['event']}] "
                f"{result['message'][:60]}..."
            )

    print(f"[proactive] Scan complete. Sent {sent_count} proactive DMs.")


async def run_scheduler(interval_seconds: int = CHECK_INTERVAL):
    """Run the proactive care check on a loop."""
    await init_db()
    print(
        f"[proactive] Starting proactive care scheduler "
        f"(interval: {interval_seconds}s, threshold: intimacy>{INTIMACY_THRESHOLD})"
    )
    while True:
        try:
            await check_and_send_proactive_dms()
        except Exception as e:
            print(f"[proactive] Error during scan: {e}")
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_scheduler())
