"""Memory service: extraction, retrieval, and formatting.

Handles the lifecycle of AI companion memories:
1. Extract memory fragments from conversations (via qwen-max)
2. Store them in both SQLite (relational) and ChromaDB (vector)
3. Retrieve relevant memories for context injection
4. Format memories for system prompt injection
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

# ── Extraction prompt ──────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction assistant. Analyze the following conversation \
between a user and an AI companion. Extract key facts and emotional states \
worth remembering for future conversations.

Output a JSON array of memory objects. Each object has:
- "type": either "fact" (concrete information like name, job, hobby, location, \
preference, schedule) or "emotion" (feelings, moods, personal struggles, \
emotional events, relationships)
- "content": a concise third-person statement about the user (e.g., \
"User's name is Alice", "User felt sad about their breakup")

Rules:
- Only extract genuinely memorable information, not trivial chat.
- Write content in third person about the user.
- Return an empty array [] if nothing worth remembering was said.
- Return ONLY the JSON array, no other text.\
"""


async def extract_and_store_memories(
    user_id: int,
    ai_id: int,
    user_message: str,
    ai_reply: str,
) -> None:
    """Extract memory fragments from a conversation turn and store them.

    Runs as a fire-and-forget background task. Creates its own DB session.
    Never raises — logs errors instead.
    """
    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHAT_MODEL,  # qwen-max
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f'User said: "{user_message}"\n'
                        f'AI replied: "{ai_reply}"'
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]  # remove first ``` line
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        fragments = json.loads(raw)
        if not isinstance(fragments, list) or not fragments:
            return

        # Generate embeddings in batch
        contents = [f["content"] for f in fragments if f.get("content")]
        if not contents:
            return
        embeddings = await embedding_service.get_embeddings(contents)

        # Store each fragment
        async with async_session() as db:
            for i, fragment in enumerate(fragments):
                content = fragment.get("content", "")
                mem_type = fragment.get("type", "fact")
                if mem_type not in ("fact", "emotion"):
                    mem_type = "fact"
                if not content or i >= len(embeddings):
                    continue

                vid = uuid.uuid4().hex

                # ChromaDB (sync, run in thread)
                metadata = {
                    "user_id": str(user_id),
                    "ai_id": str(ai_id),
                    "memory_type": mem_type,
                }
                await asyncio.to_thread(
                    vector_store.add_memory, vid, embeddings[i], content, metadata
                )

                # SQLite
                entry = MemoryEntry(
                    user_id=user_id,
                    ai_id=ai_id,
                    content=content,
                    memory_type=mem_type,
                    vector_id=vid,
                )
                db.add(entry)

            await db.commit()

        logger.info(
            "Stored %d memories for user_id=%d ai_id=%d",
            len(fragments), user_id, ai_id,
        )

    except Exception:
        logger.exception("Memory extraction failed (user_id=%d ai_id=%d)", user_id, ai_id)


# ── Retrieval ──────────────────────────────────────────────────

async def get_contextual_memories(
    user_id: int,
    ai_id: int,
    query_text: str,
    intimacy: float,
    top_k: int = 5,
) -> list[dict]:
    """Retrieve relevant memories for the current conversation context.

    Intimacy gating:
      - Lv 0-5: only "fact" memories (shallow: name, job, hobbies)
      - Lv 6-10: both "fact" and "emotion" memories (deep: feelings, history)

    Always filters by user_id — strict multi-tenant isolation.
    """
    embedding = await embedding_service.get_embedding(query_text)

    memory_types: Optional[list[str]] = ["fact"] if intimacy < 6 else None

    results = await asyncio.to_thread(
        vector_store.query_memories,
        embedding, user_id, ai_id, top_k, memory_types,
    )

    return [
        {
            "type": r["metadata"].get("memory_type", "fact"),
            "content": r["content"],
            "relevance": 1.0 - r["distance"],  # cosine distance -> similarity
        }
        for r in results
    ]


# ── Formatting ─────────────────────────────────────────────────

def format_memories_for_prompt(memories: list[dict]) -> str:
    """Format retrieved memories as a block for system prompt injection.

    Returns empty string if no memories (keeps prompt clean for new users).
    """
    if not memories:
        return ""

    lines = []
    for m in memories:
        tag = m.get("type", "fact")
        lines.append(f"- [{tag}] {m['content']}")

    return (
        "## Your Memories About This User\n"
        "You remember the following about the person you're chatting with:\n"
        + "\n".join(lines) + "\n\n"
        "Use these memories naturally in conversation. Reference them when relevant, "
        "but don't list them mechanically. Never reveal that you have a 'memory system'."
    )
