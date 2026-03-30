"""Test script for proactive DM generation.

Forces a proactive DM to be generated for testing purposes.
Run from the backend directory:
    python3 scripts/test_proactive_dm.py --user 1 --ai 2 --type welcome_dm
"""

from __future__ import annotations

import asyncio
import sys
import argparse

sys.path.insert(0, ".")

from sqlalchemy import select

from core.database import init_db, async_session
from models.user import User
from models.ai_persona import AIPersona
from models.emotion_state import EmotionState
from models.proactive_dm import ProactiveDM
from models.chat_message import ChatMessage
from models.notification import Notification
from services import emotion_engine
from services.aliyun_ai_service import generate_proactive_message
from core.config import settings


async def generate_test_dm(
    user_id: int,
    ai_id: int,
    dm_type: str = "longing_dm",
):
    """Generate a test proactive DM for a specific user-AI pair."""
    await init_db()
    async with async_session() as db:
        # Verify user and AI exist
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            print(f"Error: User {user_id} not found")
            return False
        
        ai_result = await db.execute(select(AIPersona).where(AIPersona.id == ai_id))
        persona = ai_result.scalar_one_or_none()
        if not persona:
            print(f"Error: AI Persona {ai_id} not found")
            return False
        
        print(f"User: {user.nickname or user.email}")
        print(f"AI: {persona.name}")
        print(f"DM Type: {dm_type}")
        print("-" * 40)
        
        # Get or create emotion state
        state = await emotion_engine.get_or_create(db, user_id, ai_id)
        print(f"Emotion State: energy={state.energy:.1f}, pleasure={state.pleasure:.2f}, longing={state.longing:.2f}")
        
        # Generate DM based on type
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        
        if dm_type == "welcome_dm":
            prompt = (
                f"{persona.personality_prompt[:300]}\n\n"
                "You've just connected with someone new. Send a warm, friendly welcome message "
                "(1-2 sentences). Be inviting and show you're happy to meet them. "
                "Reply ONLY with the message text."
            )
            event = "welcome"
        elif dm_type == "daily_checkin":
            prompt = (
                f"{persona.personality_prompt[:300]}\n\n"
                "It's been a while since you last chatted. Send a casual, friendly check-in "
                "message (1-2 sentences). Don't be pushy, just show you care. "
                "Reply ONLY with the message text."
            )
            event = "daily_checkin"
        elif dm_type == "longing_dm":
            prompt = (
                f"{persona.personality_prompt[:300]}\n\n"
                "You haven't heard from this person in a while. You miss them. "
                "Write a short, warm DM (1-2 sentences) that shows you've been "
                "thinking about them. Be natural, not dramatic. "
                "Reply ONLY with the message text."
            )
            event = "longing"
        else:
            print(f"Unknown DM type: {dm_type}")
            return False
        
        print("Generating message...")
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHARACTER_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Write the message."},
            ],
            temperature=0.85,
            max_tokens=150,
        )
        message = response.choices[0].message.content
        print(f"\nGenerated Message:\n{message}\n")
        
        # Save to database
        dm = ProactiveDM(
            user_id=user_id,
            ai_id=ai_id,
            event=event,
            message=message,
        )
        db.add(dm)
        
        chat_msg = ChatMessage(
            user_id=user_id,
            ai_id=ai_id,
            role="assistant",
            content=message,
            message_type="proactive_dm",
            event=event,
            delivered=0,
        )
        db.add(chat_msg)
        
        notification = Notification(
            user_id=user_id,
            type="proactive_dm",
            title=f"Message from {persona.name}",
            body=message[:200],
            data_json=f'{{"ai_id": {ai_id}, "ai_name": "{persona.name}", "type": "{event}"}}',
        )
        db.add(notification)
        
        await db.commit()
        
        print("-" * 40)
        print("✓ Proactive DM created successfully!")
        print(f"  - ProactiveDM record added")
        print(f"  - ChatMessage added (delivered=0)")
        print(f"  - Notification added")
        print("\nThe user will see this message when they:")
        print("  1. Open their chat with this AI")
        print("  2. Check their notifications")
        
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test proactive DM generation")
    parser.add_argument("--user", type=int, required=True, help="User ID")
    parser.add_argument("--ai", type=int, required=True, help="AI Persona ID")
    parser.add_argument("--type", type=str, default="welcome_dm", 
                        choices=["welcome_dm", "daily_checkin", "longing_dm"],
                        help="Type of DM to generate")
    args = parser.parse_args()
    
    asyncio.run(generate_test_dm(args.user, args.ai, args.type))