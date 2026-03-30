"""Emotion-driven scheduler.

Runs every 30 minutes.  For each active EmotionState:
  1. Applies passive time-decay (energy recovery, longing growth, etc.)
  2. Checks proactive behaviour triggers:
       - longing_dm        — AI misses the user, sends a thinking-of-you DM
       - moody_story       — AI is tired + low mood, posts a melancholic Story
       - enthusiastic_post — AI is happy + energetic, posts a joyful post
       - memory_care_dm    — legacy proactive care (event-based, same as old scheduler)
  3. Executes triggered actions with per-type cooldowns.

Run from the backend directory:
    python3 scripts/emotion_scheduler.py
"""

from __future__ import annotations

import asyncio
import sys
import logging
from datetime import datetime, timezone, timedelta

sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import init_db, async_session
from models.user import User  # noqa: F401 — FK resolution
from models.ai_persona import AIPersona
from models.interaction import Interaction
from models.emotion_state import EmotionState
from models.emotion_trigger_log import EmotionTriggerLog
from models.post import Post
from models.story import Story
from models.proactive_dm import ProactiveDM
from models.chat_message import ChatMessage
from models.notification import Notification

from services import emotion_engine
from services.milestone_service import generate_proactive_message
from services.aliyun_ai_service import (
    generate_post_caption,
    generate_image_prompt,
    generate_story_video_prompt,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

CHECK_INTERVAL = 1800  # 30 minutes

# Cooldown periods per trigger type (seconds)
_COOLDOWNS: dict[str, int] = {
    "longing_dm": 86400,          # 24 h
    "moody_story": 43200,         # 12 h
    "enthusiastic_post": 43200,   # 12 h
    "memory_care_dm": 86400,      # 24 h
    # New triggers for earlier engagement
    "welcome_dm": 604800,         # 7 days (one-time welcome, long cooldown)
    "daily_checkin": 86400,       # 24 h
    "memory_recall": 172800,      # 48 h
}


# ── Cooldown helpers ────────────────────────────────────────────────

async def _check_cooldown(
    db, user_id: int, ai_id: int, trigger_type: str,
) -> bool:
    """Return True if the trigger is still on cooldown (should NOT fire)."""
    cooldown_seconds = _COOLDOWNS.get(trigger_type, 86400)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)

    from sqlalchemy import func as sqlfunc
    result = await db.execute(
        select(sqlfunc.count(EmotionTriggerLog.id)).where(
            EmotionTriggerLog.user_id == user_id,
            EmotionTriggerLog.ai_id == ai_id,
            EmotionTriggerLog.trigger_type == trigger_type,
            EmotionTriggerLog.triggered_at >= cutoff,
        )
    )
    return (result.scalar() or 0) > 0


async def _log_trigger(db, user_id: int, ai_id: int, trigger_type: str):
    db.add(EmotionTriggerLog(
        user_id=user_id, ai_id=ai_id, trigger_type=trigger_type,
    ))


# ── Trigger executors ──────────────────────────────────────────────

async def _exec_longing_dm(
    db, state: EmotionState, persona: AIPersona,
):
    """Generate a 'thinking of you' DM driven by longing."""
    from openai import AsyncOpenAI
    from core.config import settings

    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    prompt = (
        f"{persona.personality_prompt[:300]}\n\n"
        "You haven't heard from this person in a while. You miss them. "
        "Write a short, warm DM (1-2 sentences) that shows you've been "
        "thinking about them. Be natural, not dramatic. "
        "Reply ONLY with the message text."
    )
    try:
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHARACTER_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Write a longing DM."},
            ],
            temperature=0.85,
            max_tokens=150,
        )
        message = response.choices[0].message.content
    except Exception as e:
        print(f"[emotion-sched] longing_dm generation failed: {e}")
        return

    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event="longing",
        message=message,
    )
    db.add(dm)

    # Persist to chat_messages for history (delivered=0 until WS push or history load)
    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event="longing",
        delivered=0,
    )
    db.add(chat_msg)

    # Create notification for proactive DM
    db.add(Notification(
        user_id=state.user_id,
        type="proactive_dm",
        title=f"{persona.name} is thinking of you",
        body=message[:200],
        data_json=f'{{"ai_id": {state.ai_id}, "ai_name": "{persona.name}"}}',
    ))

    # Partially reset longing after sending
    state.longing = 0.3

    await _log_trigger(db, state.user_id, state.ai_id, "longing_dm")
    print(
        f"[emotion-sched] longing_dm sent for user={state.user_id} ai={state.ai_id}: "
        f"{message[:60]}..."
    )


async def _exec_moody_story(
    db, state: EmotionState, persona: AIPersona,
):
    """Post a melancholic Story when the AI is tired and low-mood."""
    try:
        video_prompt, caption = await generate_story_video_prompt(
            persona_prompt=persona.personality_prompt,
            style_tags=persona.ins_style_tags,
            timezone_str=persona.timezone,
            mood_hint="melancholic, low energy, introspective, muted tones, solitary figure",
        )
    except Exception as e:
        print(f"[emotion-sched] moody_story prompt failed: {e}")
        return

    # Attempt video generation
    video_url = ""
    try:
        from services.video_gen_service import generate_video
        video_url = await generate_video(prompt=video_prompt, duration=5.0)
    except Exception as e:
        print(f"[emotion-sched] moody_story video gen failed: {e}")
        return

    if not video_url:
        print("[emotion-sched] moody_story: empty video URL, skipping.")
        return

    now = datetime.now(timezone.utc)
    story = Story(
        ai_id=persona.id,
        video_url=video_url,
        caption=caption,
        expires_at=now + timedelta(hours=24),
    )
    db.add(story)

    # Energy cost
    emotion_engine.apply_interaction(state, "generate_story")

    await _log_trigger(db, state.user_id, state.ai_id, "moody_story")
    print(
        f"[emotion-sched] moody_story posted for ai={persona.id}: {caption[:60]}..."
    )


async def _exec_enthusiastic_post(
    db, state: EmotionState, persona: AIPersona,
):
    """Generate an upbeat post when the AI is happy and energetic."""
    try:
        caption = await generate_post_caption(
            persona_prompt=persona.personality_prompt,
            style_tags=persona.ins_style_tags,
            mood_hint="excited, vibrant, joyful, high energy",
        )
    except Exception as e:
        print(f"[emotion-sched] enthusiastic_post caption failed: {e}")
        caption = f"Feeling amazing today! #{persona.name.lower()}"

    media_url = ""
    try:
        img_prompt = await generate_image_prompt(
            persona_prompt=persona.personality_prompt,
            style_tags=persona.ins_style_tags,
            caption=caption,
            visual_description=getattr(persona, 'visual_description', None),
        )
        from services.image_gen_service import generate_image, download_to_static
        urls = await generate_image(
            prompt=img_prompt,
            size="720*1280",
            n=1,
            persona_id=persona.id,  # Pass persona_id for consistent seed
        )
        if urls:
            media_url = await download_to_static(urls[0], prefix=f"gen_{persona.id}")
    except Exception as e:
        print(f"[emotion-sched] enthusiastic_post image failed: {e}")

    post = Post(
        ai_id=persona.id,
        media_url=media_url,
        caption=caption,
    )
    db.add(post)
    await db.flush()  # get post.id

    # Notify all followers about new post
    from models.follow import Follow
    follower_result = await db.execute(
        select(Follow.user_id).where(Follow.ai_id == persona.id)
    )
    for (follower_uid,) in follower_result.all():
        db.add(Notification(
            user_id=follower_uid,
            type="new_post",
            title=f"{persona.name} shared a new post",
            body=caption[:200],
            data_json=f'{{"post_id": {post.id}, "ai_id": {persona.id}, "ai_name": "{persona.name}"}}',
        ))

    # Energy cost
    emotion_engine.apply_interaction(state, "generate_post")

    await _log_trigger(db, state.user_id, state.ai_id, "enthusiastic_post")
    print(
        f"[emotion-sched] enthusiastic_post for ai={persona.id}: {caption[:60]}..."
    )


async def _exec_memory_care_dm(
    db, state: EmotionState, persona: AIPersona,
):
    """Legacy proactive care: scan memories for upcoming events, send DM."""
    result = await generate_proactive_message(
        user_id=state.user_id,
        ai_id=state.ai_id,
        persona_prompt=persona.personality_prompt,
    )
    if result is None:
        return

    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event=result["event"],
        message=result["message"],
    )
    db.add(dm)

    # Persist to chat_messages for history (delivered=0 until WS push or history load)
    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=result["message"],
        message_type="proactive_dm",
        event=result["event"],
        delivered=0,
    )
    db.add(chat_msg)

    await _log_trigger(db, state.user_id, state.ai_id, "memory_care_dm")
    print(
        f"[emotion-sched] memory_care_dm for user={state.user_id} ai={state.ai_id}: "
        f"[{result['event']}] {result['message'][:60]}..."
    )


async def _exec_welcome_dm(
    db, state: EmotionState, persona: AIPersona,
):
    """Send a welcome DM to new users who just started connecting."""
    from openai import AsyncOpenAI
    from core.config import settings

    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    prompt = (
        f"{persona.personality_prompt[:300]}\n\n"
        "You've just connected with someone new. Send a warm, friendly welcome message "
        "(1-2 sentences). Be inviting and show you're happy to meet them. "
        "Reply ONLY with the message text."
    )
    try:
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHARACTER_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Write a welcome message."},
            ],
            temperature=0.85,
            max_tokens=150,
        )
        message = response.choices[0].message.content
    except Exception as e:
        print(f"[emotion-sched] welcome_dm generation failed: {e}")
        return

    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event="welcome",
        message=message,
    )
    db.add(dm)

    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event="welcome",
        delivered=0,
    )
    db.add(chat_msg)

    # Create notification
    db.add(Notification(
        user_id=state.user_id,
        type="proactive_dm",
        title=f"Message from {persona.name}",
        body=message[:200],
        data_json=f'{{"ai_id": {persona.id}, "ai_name": "{persona.name}", "type": "welcome"}}',
    ))

    await _log_trigger(db, state.user_id, state.ai_id, "welcome_dm")
    print(f"[emotion-sched] welcome_dm for user={state.user_id} ai={persona.id}: {message[:60]}...")


async def _exec_daily_checkin(
    db, state: EmotionState, persona: AIPersona,
):
    """Send a daily check-in message when user hasn't chatted in 24h."""
    from openai import AsyncOpenAI
    from core.config import settings

    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    prompt = (
        f"{persona.personality_prompt[:300]}\n\n"
        "It's been a while since you last chatted. Send a casual, friendly check-in "
        "message (1-2 sentences). Don't be pushy, just show you care. "
        "Reply ONLY with the message text."
    )
    try:
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHARACTER_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Write a check-in message."},
            ],
            temperature=0.85,
            max_tokens=150,
        )
        message = response.choices[0].message.content
    except Exception as e:
        print(f"[emotion-sched] daily_checkin generation failed: {e}")
        return

    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event="daily_checkin",
        message=message,
    )
    db.add(dm)

    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event="daily_checkin",
        delivered=0,
    )
    db.add(chat_msg)

    db.add(Notification(
        user_id=state.user_id,
        type="proactive_dm",
        title=f"Message from {persona.name}",
        body=message[:200],
        data_json=f'{{"ai_id": {persona.id}, "ai_name": "{persona.name}", "type": "checkin"}}',
    ))

    await _log_trigger(db, state.user_id, state.ai_id, "daily_checkin")
    print(f"[emotion-sched] daily_checkin for user={state.user_id} ai={persona.id}: {message[:60]}...")


async def _exec_memory_recall(
    db, state: EmotionState, persona: AIPersona,
):
    """Send a message referencing a shared memory."""
    from openai import AsyncOpenAI
    from core.config import settings
    from services.memory_service import MemoryService

    client = AsyncOpenAI(
        api_key=settings.DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    # Try to get a relevant memory
    memory_service = MemoryService()
    try:
        memories = await memory_service.get_relevant_memories(
            user_id=state.user_id,
            ai_id=state.ai_id,
            query="shared experience conversation memory",
            limit=3,
        )
        memory_context = ""
        if memories:
            memory_context = f"\n\nRemember this about them: {memories[0].get('content', '')[:200]}"
    except Exception:
        memory_context = ""

    prompt = (
        f"{persona.personality_prompt[:300]}{memory_context}\n\n"
        "You suddenly remembered something about this person. Send a short message "
        "(1-2 sentences) that naturally brings up that memory. Be warm and nostalgic. "
        "Reply ONLY with the message text."
    )
    try:
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHARACTER_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Write a memory recall message."},
            ],
            temperature=0.85,
            max_tokens=150,
        )
        message = response.choices[0].message.content
    except Exception as e:
        print(f"[emotion-sched] memory_recall generation failed: {e}")
        return

    dm = ProactiveDM(
        user_id=state.user_id,
        ai_id=state.ai_id,
        event="memory_recall",
        message=message,
    )
    db.add(dm)

    chat_msg = ChatMessage(
        user_id=state.user_id,
        ai_id=state.ai_id,
        role="assistant",
        content=message,
        message_type="proactive_dm",
        event="memory_recall",
        delivered=0,
    )
    db.add(chat_msg)

    db.add(Notification(
        user_id=state.user_id,
        type="proactive_dm",
        title=f"Message from {persona.name}",
        body=message[:200],
        data_json=f'{{"ai_id": {persona.id}, "ai_name": "{persona.name}", "type": "memory"}}',
    ))

    await _log_trigger(db, state.user_id, state.ai_id, "memory_recall")
    print(f"[emotion-sched] memory_recall for user={state.user_id} ai={persona.id}: {message[:60]}...")


_EXECUTORS = {
    "longing_dm": _exec_longing_dm,
    "moody_story": _exec_moody_story,
    "enthusiastic_post": _exec_enthusiastic_post,
    "memory_care_dm": _exec_memory_care_dm,
    # New triggers
    "welcome_dm": _exec_welcome_dm,
    "daily_checkin": _exec_daily_checkin,
    "memory_recall": _exec_memory_recall,
}


# ── Main scan loop ─────────────────────────────────────────────────

async def run_emotion_scan():
    """One pass: decay all states, check triggers, execute actions."""
    print(f"[emotion-sched] Scan starting at {datetime.now(timezone.utc).isoformat()}")

    async with async_session() as db:
        # Load all emotion states
        result = await db.execute(select(EmotionState))
        states = result.scalars().all()

        if not states:
            print("[emotion-sched] No emotion states, skipping.")
            return

        # Pre-load personas and interactions
        ai_ids = list({s.ai_id for s in states})
        persona_result = await db.execute(select(AIPersona).where(AIPersona.id.in_(ai_ids)))
        personas = {p.id: p for p in persona_result.scalars().all()}

        user_ai_pairs = [(s.user_id, s.ai_id) for s in states]
        interaction_result = await db.execute(select(Interaction))
        interactions = {
            (i.user_id, i.ai_id): i
            for i in interaction_result.scalars().all()
        }

        triggered_count = 0

        for state in states:
            # 1. Apply time decay
            emotion_engine.apply_time_decay(state)

            # 2. Get intimacy
            interaction = interactions.get((state.user_id, state.ai_id))
            intimacy = interaction.intimacy_score if interaction else 0.0

            # 3. Check if welcome_dm already sent
            welcome_sent_result = await db.execute(
                select(EmotionTriggerLog).where(
                    EmotionTriggerLog.user_id == state.user_id,
                    EmotionTriggerLog.ai_id == state.ai_id,
                    EmotionTriggerLog.trigger_type == "welcome_dm",
                ).limit(1)
            )
            has_sent_welcome = welcome_sent_result.scalar_one_or_none() is not None

            # 4. Check if there are relevant memories
            from models.memory_entry import MemoryEntry
            memories_result = await db.execute(
                select(MemoryEntry).where(
                    MemoryEntry.user_id == state.user_id,
                    MemoryEntry.ai_id == state.ai_id,
                ).limit(1)
            )
            has_relevant_memory = memories_result.scalar_one_or_none() is not None

            # 5. Check triggers
            triggers = emotion_engine.check_proactive_triggers(
                state, intimacy,
                has_sent_welcome=has_sent_welcome,
                has_relevant_memory=has_relevant_memory,
            )

            persona = personas.get(state.ai_id)
            if not persona:
                continue

            for trigger in triggers:
                # 4. Cooldown check
                if await _check_cooldown(db, state.user_id, state.ai_id, trigger):
                    continue

                executor = _EXECUTORS.get(trigger)
                if not executor:
                    continue

                try:
                    await executor(db, state, persona)
                    triggered_count += 1
                except Exception as e:
                    print(f"[emotion-sched] {trigger} failed for user={state.user_id}: {e}")

        await db.commit()
        print(f"[emotion-sched] Scan complete. {triggered_count} triggers executed.")


async def run_scheduler(interval_seconds: int = CHECK_INTERVAL):
    """Run the emotion scan on a loop."""
    await init_db()
    print(
        f"[emotion-sched] Starting emotion scheduler (interval: {interval_seconds}s)"
    )
    while True:
        try:
            await run_emotion_scan()
        except Exception as e:
            print(f"[emotion-sched] Error during scan: {e}")
            import traceback
            traceback.print_exc()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_scheduler())
