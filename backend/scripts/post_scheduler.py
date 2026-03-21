"""Scheduled task: auto-generate Instagram posts with AI images for AI personas,
and Story videos with timezone-aware captions.

Posts and stories are now mood-aware: the aggregate emotion state across all
users for a given AI persona influences the generated content's tone.
"""

import asyncio
import random
from datetime import datetime, timezone, timedelta

from sqlalchemy import select

from core.database import async_session
from models.ai_persona import AIPersona
from models.post import Post
from models.story import Story
from models.emotion_state import EmotionState
from services import emotion_engine
from services.aliyun_ai_service import (
    generate_post_caption,
    generate_image_prompt,
    generate_story_video_prompt,
)
from services.image_gen_service import generate_image
from services.video_gen_service import generate_video


def _aggregate_mood_hint(states: list[EmotionState]) -> str:
    """Build a mood_hint string from aggregate emotion across all user relationships."""
    if not states:
        return ""

    avg_pleasure = sum(s.pleasure for s in states) / len(states)
    avg_activation = sum(s.activation for s in states) / len(states)
    avg_energy = sum(s.energy for s in states) / len(states)

    parts = []
    if avg_pleasure > 0.4:
        parts.append("happy, warm")
    elif avg_pleasure < -0.2:
        parts.append("slightly melancholic, reflective")

    if avg_activation > 0.3:
        parts.append("energetic, dynamic")
    elif avg_activation < -0.3:
        parts.append("calm, quiet")

    if avg_energy < 30:
        parts.append("tired, low-key")
    elif avg_energy > 75:
        parts.append("vibrant, full of life")

    return ", ".join(parts) if parts else ""


async def _apply_energy_cost_to_states(
    db, ai_id: int, event: str,
):
    """Apply energy cost for content generation to all emotion states for this AI."""
    result = await db.execute(
        select(EmotionState).where(EmotionState.ai_id == ai_id)
    )
    states = result.scalars().all()
    for s in states:
        emotion_engine.apply_interaction(s, event)


async def generate_new_post():
    """Pick an AI persona and generate a new Ins post with caption + image."""
    async with async_session() as db:
        result = await db.execute(select(AIPersona))
        personas = result.scalars().all()
        if not personas:
            print("[scheduler] No AI personas found, skipping.")
            return

        # Round-robin based on current hour
        idx = datetime.now(timezone.utc).hour % len(personas)
        persona = personas[idx]

        # ── Aggregate mood for this persona ───────────────────
        emo_result = await db.execute(
            select(EmotionState).where(EmotionState.ai_id == persona.id)
        )
        emo_states = emo_result.scalars().all()
        mood_hint = _aggregate_mood_hint(emo_states)

        # Step 1: Generate caption (mood-aware)
        try:
            caption = await generate_post_caption(
                persona_prompt=persona.personality_prompt,
                style_tags=persona.ins_style_tags,
                mood_hint=mood_hint,
            )
        except Exception as e:
            print(f"[scheduler] Caption generation failed: {e}")
            caption = f"Living my best life. #{persona.name.lower()}"

        # Step 2: Generate image prompt
        media_url = ""
        try:
            img_prompt = await generate_image_prompt(
                persona_prompt=persona.personality_prompt,
                style_tags=persona.ins_style_tags,
                caption=caption,
            )
            print(f"[scheduler] Image prompt: {img_prompt[:80]}...")

            # Step 3: Generate image (4:5 portrait like Instagram)
            urls = await generate_image(prompt=img_prompt, size="720*1280", n=1)
            media_url = urls[0] if urls else ""
            print(f"[scheduler] Image generated: {media_url[:80]}...")
        except Exception as e:
            print(f"[scheduler] Image generation failed: {e}")

        # Step 4: Save post
        post = Post(
            ai_id=persona.id,
            media_url=media_url,
            caption=caption,
        )
        db.add(post)

        # Step 5: Apply energy cost to all emotion states for this AI
        await _apply_energy_cost_to_states(db, persona.id, "generate_post")

        await db.commit()
        print(f"[scheduler] New post by {persona.name}: {caption[:60]}...")


async def generate_new_story():
    """Pick a random AI persona and generate a Story video with timezone-aware caption."""
    async with async_session() as db:
        result = await db.execute(select(AIPersona))
        personas = result.scalars().all()
        if not personas:
            print("[story-scheduler] No AI personas found, skipping.")
            return

        persona = random.choice(personas)
        print(f"[story-scheduler] Generating story for {persona.name} (tz={persona.timezone})...")

        # ── Aggregate mood for this persona ───────────────────
        emo_result = await db.execute(
            select(EmotionState).where(EmotionState.ai_id == persona.id)
        )
        emo_states = emo_result.scalars().all()
        mood_hint = _aggregate_mood_hint(emo_states)

        # Step 1: Generate video prompt + caption (timezone + mood aware)
        try:
            video_prompt, caption = await generate_story_video_prompt(
                persona_prompt=persona.personality_prompt,
                style_tags=persona.ins_style_tags,
                timezone_str=persona.timezone,
                mood_hint=mood_hint,
            )
            print(f"[story-scheduler] Video prompt: {video_prompt[:80]}...")
            print(f"[story-scheduler] Caption: {caption[:60]}")
        except Exception as e:
            print(f"[story-scheduler] Prompt generation failed: {e}")
            return

        # Step 2: Generate video via Wanx Video
        video_url = ""
        try:
            video_url = await generate_video(prompt=video_prompt, duration=5.0)
            print(f"[story-scheduler] Video generated: {video_url[:80]}...")
        except Exception as e:
            print(f"[story-scheduler] Video generation failed: {e}")
            return

        if not video_url:
            print("[story-scheduler] Empty video URL, skipping.")
            return

        # Step 3: Save story with 24h expiry
        now = datetime.now(timezone.utc)
        story = Story(
            ai_id=persona.id,
            video_url=video_url,
            caption=caption,
            expires_at=now + timedelta(hours=24),
        )
        db.add(story)

        # Step 4: Apply energy cost to all emotion states for this AI
        await _apply_energy_cost_to_states(db, persona.id, "generate_story")

        await db.commit()
        print(f"[story-scheduler] New story by {persona.name}: {caption[:60]}...")


async def run_scheduler(interval_seconds: int = 3600):
    """Simple async scheduler loop — posts every hour, stories every 12 hours."""
    print(f"[scheduler] Starting post generation every {interval_seconds}s")
    print("[scheduler] Starting story generation every 12h")
    story_interval = 12 * 3600  # 12 hours
    last_story_time = 0.0

    while True:
        await generate_new_post()

        # Generate story every 12 hours (2 per day)
        now = asyncio.get_event_loop().time()
        if now - last_story_time >= story_interval:
            try:
                await generate_new_story()
            except Exception as e:
                print(f"[story-scheduler] Error: {e}")
            last_story_time = now

        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    asyncio.run(run_scheduler(interval_seconds=3600))
