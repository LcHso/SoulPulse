"""Test script: verify multi-tenant memory isolation.

Proves that User A's memories are never leaked to User B.
Run from the backend directory:
    python3 scripts/test_memory_isolation.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid

# Allow running from backend/ directory
sys.path.insert(0, ".")

from core.database import init_db, async_session
from core.security import hash_password
from models.user import User
from models.ai_persona import AIPersona
from models.memory_entry import MemoryEntry
from services import embedding_service, vector_store
from services.memory_service import get_contextual_memories

# ── ANSI colors ──
GREEN = "\033[92m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}: {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}FAIL{RESET}: {msg}")


async def setup_test_users(db) -> tuple[int, int, int]:
    """Create two test users and one AI persona, return their IDs."""
    from sqlalchemy import select

    # Check for existing test persona
    result = await db.execute(select(AIPersona).limit(1))
    persona = result.scalar_one_or_none()
    if not persona:
        persona = AIPersona(
            name="TestBot",
            personality_prompt="A friendly test companion.",
            bio="Test persona",
        )
        db.add(persona)
        await db.commit()
        await db.refresh(persona)

    # Create test users
    user_a = User(
        email=f"test_a_{uuid.uuid4().hex[:6]}@test.com",
        hashed_password=hash_password("pass"),
        nickname="Alice",
    )
    user_b = User(
        email=f"test_b_{uuid.uuid4().hex[:6]}@test.com",
        hashed_password=hash_password("pass"),
        nickname="Bob",
    )
    db.add_all([user_a, user_b])
    await db.commit()
    await db.refresh(user_a)
    await db.refresh(user_b)

    return user_a.id, user_b.id, persona.id


async def store_test_memories(user_id: int, ai_id: int, memories: list[dict]) -> None:
    """Store a list of memories for a given user, in both SQLite and ChromaDB."""
    contents = [m["content"] for m in memories]
    embeddings = await embedding_service.get_embeddings(contents)

    async with async_session() as db:
        for i, mem in enumerate(memories):
            vid = uuid.uuid4().hex
            metadata = {
                "user_id": str(user_id),
                "ai_id": str(ai_id),
                "memory_type": mem["type"],
            }
            await asyncio.to_thread(
                vector_store.add_memory, vid, embeddings[i], mem["content"], metadata
            )
            entry = MemoryEntry(
                user_id=user_id,
                ai_id=ai_id,
                content=mem["content"],
                memory_type=mem["type"],
                vector_id=vid,
            )
            db.add(entry)
        await db.commit()


async def run_tests() -> None:
    print(f"\n{BOLD}=== SoulPulse Memory Isolation Test ==={RESET}\n")

    await init_db()

    async with async_session() as db:
        user_a_id, user_b_id, ai_id = await setup_test_users(db)

    print(f"User A (Alice): id={user_a_id}")
    print(f"User B (Bob):   id={user_b_id}")
    print(f"AI Persona:     id={ai_id}\n")

    # ── Store memories ──────────────────────────────────────
    print(f"{BOLD}Step 1: Storing memories{RESET}")

    user_a_memories = [
        {"type": "fact", "content": "User's name is Alice"},
        {"type": "fact", "content": "User's favorite color is blue"},
        {"type": "fact", "content": "User works as a teacher"},
        {"type": "emotion", "content": "User felt happy about her promotion"},
    ]
    await store_test_memories(user_a_id, ai_id, user_a_memories)
    print(f"  Stored {len(user_a_memories)} memories for User A (Alice)")

    user_b_memories = [
        {"type": "fact", "content": "User's name is Bob"},
        {"type": "fact", "content": "User's favorite color is red"},
        {"type": "fact", "content": "User is a software engineer"},
        {"type": "emotion", "content": "User is stressed about deadlines"},
    ]
    await store_test_memories(user_b_id, ai_id, user_b_memories)
    print(f"  Stored {len(user_b_memories)} memories for User B (Bob)")

    all_passed = True

    # ── Test 1: User A query ────────────────────────────────
    print(f"\n{BOLD}Step 2: Retrieval isolation tests{RESET}")

    print(f"\n  [TEST 1] Query: \"What is the user's job?\" | Filter: user_id={user_a_id}")
    results_a = await get_contextual_memories(
        user_id=user_a_id, ai_id=ai_id,
        query_text="What is the user's job?",
        intimacy=3.0,  # low intimacy — only facts
    )
    print(f"  Results ({len(results_a)}):")
    for r in results_a:
        print(f"    [{r['type']}] {r['content']}  (relevance: {r['relevance']:.3f})")

    # Check no Bob data in Alice's results
    a_contents = " ".join(r["content"] for r in results_a)
    if "Bob" in a_contents or "software engineer" in a_contents or "red" in a_contents:
        fail("User A results contain User B data!")
        all_passed = False
    else:
        ok("No cross-tenant contamination")

    # ── Test 2: User B query ────────────────────────────────
    print(f"\n  [TEST 2] Query: \"How is the user feeling?\" | Filter: user_id={user_b_id}")
    results_b = await get_contextual_memories(
        user_id=user_b_id, ai_id=ai_id,
        query_text="How is the user feeling?",
        intimacy=8.0,  # high intimacy — facts + emotions
    )
    print(f"  Results ({len(results_b)}):")
    for r in results_b:
        print(f"    [{r['type']}] {r['content']}  (relevance: {r['relevance']:.3f})")

    b_contents = " ".join(r["content"] for r in results_b)
    if "Alice" in b_contents or "teacher" in b_contents or "blue" in b_contents or "promotion" in b_contents:
        fail("User B results contain User A data!")
        all_passed = False
    else:
        ok("No cross-tenant contamination")

    # ── Test 3: Intimacy gating ─────────────────────────────
    print(f"\n  [TEST 3] Intimacy gating: User B at low intimacy (3.0)")
    results_b_low = await get_contextual_memories(
        user_id=user_b_id, ai_id=ai_id,
        query_text="How is the user feeling?",
        intimacy=3.0,  # low — should only get facts, no emotions
    )
    print(f"  Results ({len(results_b_low)}):")
    for r in results_b_low:
        print(f"    [{r['type']}] {r['content']}  (relevance: {r['relevance']:.3f})")

    emotion_types = [r for r in results_b_low if r["type"] == "emotion"]
    if emotion_types:
        fail(f"Low intimacy returned {len(emotion_types)} emotion memories!")
        all_passed = False
    else:
        ok("No emotion memories returned at low intimacy")

    # ── Test 4: Cross-query — User A searching for Bob's data ──
    print(f"\n  [TEST 4] Cross-query: User A searches for \"Bob cooking red\" | Filter: user_id={user_a_id}")
    results_cross = await get_contextual_memories(
        user_id=user_a_id, ai_id=ai_id,
        query_text="Bob cooking red favorite color",
        intimacy=10.0,
    )
    print(f"  Results ({len(results_cross)}):")
    for r in results_cross:
        print(f"    [{r['type']}] {r['content']}  (relevance: {r['relevance']:.3f})")

    cross_contents = " ".join(r["content"] for r in results_cross)
    if "Bob" in cross_contents or "red" in cross_contents or "software engineer" in cross_contents:
        fail("Cross-query returned User B data for User A!")
        all_passed = False
    else:
        ok("Cross-query correctly returned only User A data (or empty)")

    # ── Test 5: SQLite isolation ────────────────────────────
    print(f"\n  [TEST 5] SQLite direct query isolation")
    from sqlalchemy import select
    async with async_session() as db:
        result = await db.execute(
            select(MemoryEntry).where(MemoryEntry.user_id == user_a_id)
        )
        a_entries = result.scalars().all()
        print(f"  User A SQLite entries: {len(a_entries)}")

        result = await db.execute(
            select(MemoryEntry).where(MemoryEntry.user_id == user_b_id)
        )
        b_entries = result.scalars().all()
        print(f"  User B SQLite entries: {len(b_entries)}")

        # Verify no cross-contamination
        a_db_contents = " ".join(e.content for e in a_entries)
        b_db_contents = " ".join(e.content for e in b_entries)

        if "Bob" in a_db_contents or "red" in a_db_contents:
            fail("User A SQLite entries contain User B data!")
            all_passed = False
        elif "Alice" in b_db_contents or "blue" in b_db_contents:
            fail("User B SQLite entries contain User A data!")
            all_passed = False
        else:
            ok("SQLite data is correctly isolated")

    # ── Summary ─────────────────────────────────────────────
    print(f"\n{BOLD}{'=' * 40}{RESET}")
    if all_passed:
        print(f"{GREEN}{BOLD}ALL TESTS PASSED — Memory isolation verified!{RESET}")
    else:
        print(f"{RED}{BOLD}SOME TESTS FAILED — Check above for details{RESET}")
    print()


if __name__ == "__main__":
    asyncio.run(run_tests())
