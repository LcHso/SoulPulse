"""Relationship milestone service.

Handles:
1. Nickname proposal — when intimacy crosses Lv 6, AI proposes a special
   nickname based on long-term memories about the user.
2. Proactive care — scans memories for upcoming events / schedules and
   generates caring DM messages for high-intimacy users.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Optional

from core.config import settings
from core.database import async_session
from models.memory_entry import MemoryEntry
from services import embedding_service, vector_store
from services.aliyun_ai_service import _get_client

logger = logging.getLogger(__name__)

# ── Nickname proposal ──────────────────────────────────────────

_NICKNAME_PROPOSAL_PROMPT = """\
You are an AI companion who just became close friends with a user.
Based on the memories you have about this user, propose ONE special \
nickname (专属称呼) that is:
- Warm, creative, and personal — inspired by something you know about them
- Not generic (avoid 宝贝, 亲爱的, honey, baby)
- Between 2-4 Chinese characters (or 1-2 English words if appropriate)

Also write a short, sweet in-character message (1-2 sentences) proposing \
this nickname. Speak as yourself, naturally.

Return a JSON object with exactly two keys:
- "nickname": the proposed nickname string
- "message": your proposal message to the user

Return ONLY the JSON object, nothing else.\
"""


async def propose_nickname(
    user_id: int,
    ai_id: int,
    persona_prompt: str,
    user_nickname: str,
) -> Optional[dict]:
    """Generate a nickname proposal using long-term memories.

    Returns {"nickname": "...", "message": "..."} or None on failure.
    """
    try:
        # Fetch user's fact memories for context
        memories = await _get_user_memories_text(user_id, ai_id, limit=10)
        if not memories:
            memories = f"User's display name is {user_nickname}."

        client = _get_client()
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHAT_MODEL,  # qwen-max for quality
            messages=[
                {"role": "system", "content": _NICKNAME_PROPOSAL_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Your character: {persona_prompt[:300]}\n\n"
                        f"User's display name: {user_nickname}\n\n"
                        f"Your memories about this user:\n{memories}"
                    ),
                },
            ],
            temperature=0.8,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        if "nickname" in result and "message" in result:
            return result

        logger.warning("Nickname proposal missing required keys: %s", raw)
        return None

    except Exception:
        logger.exception(
            "Nickname proposal failed (user_id=%d ai_id=%d)", user_id, ai_id
        )
        return None


async def persist_nickname_to_memory(
    user_id: int, ai_id: int, nickname: str
) -> None:
    """Store the unlocked nickname as a fact memory for future consistency."""
    content = f"AI gave the user a special nickname: '{nickname}'. Always use this nickname naturally in conversation."
    try:
        embedding = await embedding_service.get_embedding(content)
        vid = uuid.uuid4().hex
        metadata = {
            "user_id": str(user_id),
            "ai_id": str(ai_id),
            "memory_type": "fact",
        }
        await asyncio.to_thread(
            vector_store.add_memory, vid, embedding, content, metadata
        )
        async with async_session() as db:
            entry = MemoryEntry(
                user_id=user_id,
                ai_id=ai_id,
                content=content,
                memory_type="fact",
                vector_id=vid,
            )
            db.add(entry)
            await db.commit()

        logger.info(
            "Persisted nickname '%s' to memory (user_id=%d ai_id=%d)",
            nickname, user_id, ai_id,
        )
    except Exception:
        logger.exception("Failed to persist nickname to memory")


# ── Proactive care ─────────────────────────────────────────────

_PROACTIVE_CARE_PROMPT = """\
You are an AI companion who cares deeply about a user. Based on the \
memories below, determine if there is an upcoming event, appointment, \
exam, meeting, or important date that the user mentioned.

If yes, write a short caring DM message (1-3 sentences) showing that \
you remembered and care. Speak as yourself, naturally and warmly.

If there is nothing time-sensitive or relevant, return exactly: null

Return a JSON object with:
- "event": brief description of the event you're referencing
- "message": your caring DM message

Or return: null (if no relevant event found)

Return ONLY the JSON or null, nothing else.\
"""


async def generate_proactive_message(
    user_id: int,
    ai_id: int,
    persona_prompt: str,
) -> Optional[dict]:
    """Check memories for schedule-related content and generate a caring DM.

    Returns {"event": "...", "message": "..."} or None if nothing relevant.
    """
    try:
        # Search for schedule-related memories
        schedule_query = "考试 开会 面试 约会 旅行 deadline 比赛 搬家 exam meeting interview appointment"
        embedding = await embedding_service.get_embedding(schedule_query)

        results = await asyncio.to_thread(
            vector_store.query_memories,
            embedding, user_id, ai_id, 8, None,  # top 8, all types
        )

        if not results:
            return None

        memories_text = "\n".join(
            f"- [{r['metadata'].get('memory_type', 'fact')}] {r['content']}"
            for r in results
        )

        client = _get_client()
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHAT_MODEL,
            messages=[
                {"role": "system", "content": _PROACTIVE_CARE_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Your character: {persona_prompt[:300]}\n\n"
                        f"User memories:\n{memories_text}"
                    ),
                },
            ],
            temperature=0.7,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        if raw.lower() == "null":
            return None

        result = json.loads(raw)
        if "event" in result and "message" in result:
            return result

        return None

    except Exception:
        logger.exception(
            "Proactive care generation failed (user_id=%d ai_id=%d)",
            user_id, ai_id,
        )
        return None


# ── Helpers ────────────────────────────────────────────────────

async def _get_user_memories_text(
    user_id: int, ai_id: int, limit: int = 10
) -> str:
    """Fetch recent memories for a user as a text block."""
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(MemoryEntry)
            .where(MemoryEntry.user_id == user_id, MemoryEntry.ai_id == ai_id)
            .order_by(MemoryEntry.created_at.desc())
            .limit(limit)
        )
        entries = result.scalars().all()

    if not entries:
        return ""

    return "\n".join(f"- [{e.memory_type}] {e.content}" for e in entries)
