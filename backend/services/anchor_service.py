"""Anchor service: extraction, detection, formatting, and management.

Handles the lifecycle of relational anchors (emotional sensitivities):
1. Extract anchors from conversations (via qwen-max) — fire-and-forget
2. Deduplicate against existing anchors (cosine similarity in ChromaDB)
3. Detect which anchors are active given a conversation context
4. Build prompt directives (prevention + repair)
5. Detect user sentiment (keyword-based, no LLM)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import async_session
from models.relational_anchor import RelationalAnchor
from services import embedding_service, vector_store
from services.aliyun_ai_service import _get_client

logger = logging.getLogger(__name__)

# ── Extraction prompt ──────────────────────────────────────────

_ANCHOR_EXTRACTION_PROMPT = """\
You are a relationship sensitivity analyst. Analyze the following conversation \
between a user and their AI companion. Identify any relational sensitivities \
that the AI should remember and respect in future conversations.

Extract sensitivities as a JSON array of objects. Each object has:
- "type": one of "taboo" (topics the user dislikes or reacts negatively to), \
"preference" (things the user particularly likes or values), \
"fear" (anxieties, insecurities, or worries the user has revealed), \
"boundary" (explicit limits the user has expressed)
- "content": a concise third-person description (e.g., \
"User doesn't like being compared to other people", \
"User is sensitive about their weight")
- "severity": integer 1-5 (1=mild preference, 5=hard boundary/deep fear)

Rules:
- Only extract genuine sensitivities, not trivial preferences.
- Most conversations will have NOTHING to extract — return [] in that case.
- Write content in third person about the user.
- Return ONLY the JSON array, no other text.\
"""

# ── Sentiment detection keywords ──────────────────────────────

_NEGATIVE_KEYWORDS = (
    # Chinese
    "不开心", "难过", "别这样", "讨厌", "生气", "烦", "恼火",
    "伤心", "不高兴", "不喜欢", "受伤", "委屈", "失望", "无语",
    "别提了", "够了", "不要", "不想", "滚", "闭嘴",
    # English
    "upset", "hate", "stop", "hurt", "angry", "annoying", "annoyed",
    "don't", "disappointed", "sad", "frustrated", "shut up",
    "leave me", "not funny", "that's rude", "offensive",
)

_POSITIVE_KEYWORDS = (
    # Chinese
    "开心", "高兴", "喜欢", "爱你", "好棒", "太好了", "感动",
    "幸福", "谢谢", "感谢", "温暖", "安心",
    # English
    "happy", "love", "great", "wonderful", "amazing", "thank",
    "appreciate", "sweet", "adorable", "perfect",
)

# ── Dedup threshold ────────────────────────────────────────────
_DEDUP_DISTANCE_THRESHOLD = 0.15  # cosine distance < 0.15 = same anchor

# ── Detection threshold ────────────────────────────────────────
_ACTIVE_SIMILARITY_THRESHOLD = 0.35  # 1 - distance >= 0.35 = anchor active

# ── Anchor type emoji map (for prompt formatting) ──────────────
_ANCHOR_EMOJI = {
    "taboo": "\u26a0\ufe0f",
    "preference": "\U0001f49b",
    "fear": "\U0001f6e1\ufe0f",
    "boundary": "\U0001f6d1",
}


# ═══════════════════════════════════════════════════════════════
# Extraction (fire-and-forget background task)
# ═══════════════════════════════════════════════════════════════

async def extract_and_store_anchors(
    user_id: int,
    ai_id: int,
    user_message: str,
    ai_reply: str,
) -> None:
    """Extract relational anchors from a conversation turn and store them.

    Runs as a fire-and-forget background task. Creates its own DB session.
    Deduplicates against existing anchors in ChromaDB.
    Never raises — logs errors instead.
    """
    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHAT_MODEL,
            messages=[
                {"role": "system", "content": _ANCHOR_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f'User said: "{user_message}"\n'
                        f'AI replied: "{ai_reply}"'
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=400,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        fragments = json.loads(raw)
        if not isinstance(fragments, list) or not fragments:
            return

        # Validate and filter
        valid_types = {"taboo", "preference", "fear", "boundary"}
        anchors = []
        for f in fragments:
            atype = f.get("type", "")
            content = f.get("content", "").strip()
            severity = f.get("severity", 3)
            if atype not in valid_types or not content:
                continue
            severity = max(1, min(5, int(severity)))
            anchors.append({"type": atype, "content": content, "severity": severity})

        if not anchors:
            return

        # Embed all anchor contents
        contents = [a["content"] for a in anchors]
        embeddings = await embedding_service.get_embeddings(contents)

        # Store with dedup
        async with async_session() as db:
            stored = 0
            for i, anchor in enumerate(anchors):
                if i >= len(embeddings):
                    break

                emb = embeddings[i]

                # Dedup: check if a very similar anchor already exists
                existing = await asyncio.to_thread(
                    vector_store.query_anchor_by_content, emb, user_id, ai_id,
                )
                if existing and existing["distance"] < _DEDUP_DISTANCE_THRESHOLD:
                    # Similar anchor exists — just touch updated_at
                    existing_vid = existing["metadata"].get("vector_id", "")
                    if existing_vid:
                        await db.execute(
                            update(RelationalAnchor)
                            .where(RelationalAnchor.vector_id == existing_vid)
                            .values(updated_at=datetime.now(timezone.utc))
                        )
                    continue

                vid = uuid.uuid4().hex

                # ChromaDB
                metadata = {
                    "user_id": str(user_id),
                    "ai_id": str(ai_id),
                    "anchor_type": anchor["type"],
                    "vector_id": vid,
                }
                await asyncio.to_thread(
                    vector_store.add_anchor, vid, emb, anchor["content"], metadata,
                )

                # SQLite
                entry = RelationalAnchor(
                    user_id=user_id,
                    ai_id=ai_id,
                    anchor_type=anchor["type"],
                    content=anchor["content"],
                    severity=anchor["severity"],
                    vector_id=vid,
                )
                db.add(entry)
                stored += 1

            await db.commit()

        if stored:
            logger.info(
                "Stored %d anchors for user_id=%d ai_id=%d",
                stored, user_id, ai_id,
            )

    except Exception:
        logger.exception("Anchor extraction failed (user_id=%d ai_id=%d)", user_id, ai_id)


# ═══════════════════════════════════════════════════════════════
# Loading (from SQLite)
# ═══════════════════════════════════════════════════════════════

async def load_anchors(
    db: AsyncSession,
    user_id: int,
    ai_id: int,
) -> list[RelationalAnchor]:
    """Load all relational anchors for a user-AI pair, ordered by severity."""
    result = await db.execute(
        select(RelationalAnchor)
        .where(
            RelationalAnchor.user_id == user_id,
            RelationalAnchor.ai_id == ai_id,
        )
        .order_by(RelationalAnchor.severity.desc())
    )
    return list(result.scalars().all())


# ═══════════════════════════════════════════════════════════════
# Detection (hot path — uses ChromaDB vector similarity)
# ═══════════════════════════════════════════════════════════════

async def detect_active_anchors(
    anchors: list[RelationalAnchor],
    context_embedding: list[float],
    user_id: int,
    ai_id: int,
    threshold: float = _ACTIVE_SIMILARITY_THRESHOLD,
) -> list[RelationalAnchor]:
    """Detect which anchors are relevant to the current conversation context.

    Uses vector similarity between the context embedding and anchor embeddings
    in ChromaDB. Returns anchors whose similarity >= threshold.
    """
    if not anchors:
        return []

    # Query anchor collection for matches
    results = await asyncio.to_thread(
        vector_store.query_anchors,
        context_embedding, user_id, ai_id, top_k=len(anchors),
    )

    if not results:
        return []

    # Build a set of vector_ids that are above threshold
    active_vids: set[str] = set()
    for r in results:
        similarity = 1.0 - r["distance"]
        if similarity >= threshold:
            vid = r["metadata"].get("vector_id", "")
            if vid:
                active_vids.add(vid)

    # Match back to loaded anchor objects
    return [a for a in anchors if a.vector_id in active_vids]


# ═══════════════════════════════════════════════════════════════
# Sentiment detection (keyword-based, no LLM)
# ═══════════════════════════════════════════════════════════════

def detect_sentiment(message: str) -> str:
    """Detect basic sentiment of a user message via keyword matching.

    Returns "negative", "positive", or "neutral".
    Uses substring matching — fast, no API calls.
    """
    msg_lower = message.lower()

    neg_hits = sum(1 for kw in _NEGATIVE_KEYWORDS if kw in msg_lower)
    pos_hits = sum(1 for kw in _POSITIVE_KEYWORDS if kw in msg_lower)

    if neg_hits > pos_hits and neg_hits > 0:
        return "negative"
    if pos_hits > neg_hits and pos_hits > 0:
        return "positive"
    return "neutral"


# ═══════════════════════════════════════════════════════════════
# Directive formatting (for system prompt injection)
# ═══════════════════════════════════════════════════════════════

def build_anchor_directives(
    active_anchors: list[RelationalAnchor],
    all_anchors: list[RelationalAnchor],
    sentiment: str,
) -> str:
    """Build anchor-related prompt sections for system prompt injection.

    Returns a combined string containing:
      - Prevention section (always, if any anchors exist)
      - Repair section (only if active anchor + negative sentiment)

    Returns empty string if no anchors at all.
    """
    if not all_anchors:
        return ""

    parts: list[str] = []

    # ── Section A: Prevention (always present) ─────────────────
    prevention_lines = []
    for a in all_anchors:
        emoji = _ANCHOR_EMOJI.get(a.anchor_type, "\u2022")
        prevention_lines.append(
            f"- {emoji} [{a.anchor_type}/sev:{a.severity}] {a.content}"
        )

    parts.append(
        "## Relationship Boundaries\n"
        "Be mindful of these known sensitivities about this user. "
        "Avoid triggering them in conversation:\n"
        + "\n".join(prevention_lines)
    )

    # ── Section B: Repair (only if anchor triggered + negative) ─
    if active_anchors and sentiment == "negative":
        # Use the highest-severity active anchor for the repair alert
        primary = max(active_anchors, key=lambda a: a.severity)
        parts.append(
            "## \u26a0\ufe0f ANCHOR ALERT \u2014 HANDLE WITH CARE\n"
            f'You just touched on a sensitive area: "{primary.content}"\n'
            "The user seems upset. Immediately:\n"
            "1. Acknowledge sincerely (don't over-apologize or grovel)\n"
            "2. Show that you remember and respect this boundary\n"
            "3. Gently redirect the conversation toward comfort\n"
            "Do NOT be defensive. Do NOT explain why you said it. "
            "Focus entirely on the user's feelings."
        )

    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# Hit count tracking (background)
# ═══════════════════════════════════════════════════════════════

async def increment_hit_counts_bg(
    user_id: int,
    ai_id: int,
    anchor_ids: list[int],
) -> None:
    """Bump hit_count on triggered anchors. Runs as fire-and-forget."""
    try:
        async with async_session() as db:
            for aid in anchor_ids:
                await db.execute(
                    update(RelationalAnchor)
                    .where(RelationalAnchor.id == aid)
                    .values(hit_count=RelationalAnchor.hit_count + 1)
                )
            await db.commit()
    except Exception:
        logger.exception(
            "Failed to update anchor hit counts (user_id=%d ai_id=%d)",
            user_id, ai_id,
        )
