"""Seed script to insert a default AI persona for testing."""

import asyncio
from core.database import async_session, init_db
from models.ai_persona import AIPersona
from sqlalchemy import select


async def seed():
    await init_db()
    async with async_session() as db:
        existing = await db.execute(select(AIPersona).limit(1))
        if existing.scalar_one_or_none():
            print("[seed] AI persona already exists, skipping.")
            return

        persona = AIPersona(
            name="Ethan",
            bio="Photographer & coffee enthusiast based in London",
            profession="Photographer",
            personality_prompt=(
                "You are Ethan, a 26-year-old photographer living in London. "
                "You are warm, artistic, and slightly romantic. You love street photography, "
                "specialty coffee, and late-night jazz. You speak casually, sometimes using "
                "British slang. You care deeply about the people you connect with."
            ),
            gender_tag="male",
            ins_style_tags="photography, coffee, london, jazz, golden-hour, film-camera",
            avatar_url="",
            timezone="Europe/London",
        )
        db.add(persona)
        await db.commit()
        print(f"[seed] Created AI persona: {persona.name}")


if __name__ == "__main__":
    asyncio.run(seed())
