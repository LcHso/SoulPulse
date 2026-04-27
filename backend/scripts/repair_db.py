"""
Database repair script: Fix widespread B-tree page corruption.

The corrupted DB has B-tree pages swapped between multiple tables.
This script:
1. Creates a clean DB with correct schema via init_db()
2. Recovers users ↔ ai_personas swap from temp DB + lost_and_found
3. Copies correct tables (interactions, posts, stories) from temp DB
4. Recovers emotion_states, emotion_trigger_logs, relational_anchors from lost_and_found
5. Applies updated persona prompts from seed_personas.py
"""
import asyncio
import sys
import os
import sqlite3

sys.path.insert(0, ".")


async def repair():
    # --- Step 1: Create clean DB with ORM schema ---
    new_db = "soulpulse_new.db"
    if os.path.exists(new_db):
        os.remove(new_db)

    from core.config import settings
    orig_url = settings.DATABASE_URL
    settings.DATABASE_URL = f"sqlite+aiosqlite:///{new_db}"

    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from core import database as db_mod

    db_mod.engine = create_async_engine(settings.DATABASE_URL, echo=False)
    db_mod.async_session = async_sessionmaker(
        db_mod.engine, class_=AsyncSession, expire_on_commit=False,
    )
    await db_mod.init_db()
    await db_mod.engine.dispose()
    settings.DATABASE_URL = orig_url
    print(f"[repair] Clean DB created: {new_db}")

    # --- Step 2: Open connections ---
    temp = sqlite3.connect("/tmp/soulpulse_temp.db")
    temp.row_factory = sqlite3.Row
    recover = sqlite3.connect("soulpulse_recover.db")
    new = sqlite3.connect(new_db)

    # Get new DB schema info
    new_tables = {}
    for row in new.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
        cols = [r[1] for r in new.execute(f"PRAGMA table_info({row[0]})").fetchall()]
        new_tables[row[0]] = cols
    print(f"[repair] New DB has {len(new_tables)} tables")

    # ═══════════════════════════════════════════════════════════════
    # Step 3: Fix users ↔ ai_personas swap
    # ═══════════════════════════════════════════════════════════════

    # 3a: temp.ai_personas → new.users
    # Physical tuple mapping (verified empirically):
    #   name=email, bio=hashed_password, profession=nickname,
    #   personality_prompt=orientation_preference, gender_tag=gem_balance,
    #   ins_style_tags=created_at, avatar_url=(empty),
    #   timezone=gender, created_at=is_admin ("1" or "")
    print("[repair] Mapping temp.ai_personas → new.users ...")
    rows = temp.execute("SELECT * FROM ai_personas").fetchall()
    for r in rows:
        is_admin_val = 1 if str(r["created_at"]).strip() == "1" else 0
        gender_val = r["timezone"] if r["timezone"] else "not_specified"
        new.execute(
            """INSERT INTO users
               (id, email, hashed_password, nickname, avatar_url, gender,
                orientation_preference, gem_balance, is_admin, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (r["id"], r["name"], r["bio"], r["profession"],
             "", gender_val, r["personality_prompt"],
             r["gender_tag"], is_admin_val, r["ins_style_tags"]),
        )
    print(f"  -> {len(rows)} users inserted")

    # 3b: lost_and_found rootpgno=3 → new.ai_personas (full data with all columns)
    print("[repair] Recovering ai_personas from lost_and_found ...")
    lf_rows = recover.execute(
        "SELECT id, c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11, c12, c13, c14, c15, c16 "
        "FROM lost_and_found WHERE rootpgno=3 AND nfield=17"
    ).fetchall()
    for lf in lf_rows:
        # c1=name, c2=bio, c3=profession, c4=personality_prompt,
        # c5=gender_tag, c6=category, c7=archetype, c8=ins_style_tags,
        # c9=avatar_url, c10=timezone, c11=sort_order, c12=is_active,
        # c13=created_at, c14=visual_description, c15=base_face_url,
        # c16=visual_prompt_tags
        new.execute(
            """INSERT INTO ai_personas
               (id, name, bio, profession, personality_prompt, gender_tag,
                category, archetype, ins_style_tags, visual_description,
                base_face_url, visual_prompt_tags, avatar_url, timezone,
                sort_order, is_active, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (lf[0], lf[1], lf[2], lf[3], lf[4], lf[5],
             lf[6], lf[7], lf[8], lf[14],
             lf[15], lf[16], lf[9], lf[10],
             lf[11], lf[12], lf[13]),
        )
    print(f"  -> {len(lf_rows)} ai_personas inserted")

    # ═══════════════════════════════════════════════════════════════
    # Step 4: Copy CORRECT tables from temp DB
    # Only interactions, posts, stories are verified correct in temp DB.
    # chat_messages, chat_summaries, emotion_trigger_logs are corrupted.
    # ═══════════════════════════════════════════════════════════════
    correct_temp_tables = ["interactions", "posts", "stories"]
    for tbl in correct_temp_tables:
        temp_cols = [r[1] for r in temp.execute(f"PRAGMA table_info({tbl})").fetchall()]
        new_cols = new_tables.get(tbl, [])
        common = [c for c in temp_cols if c in new_cols]
        col_list = ", ".join(common)
        placeholders = ", ".join(["?"] * len(common))
        rows = temp.execute(f"SELECT {col_list} FROM {tbl}").fetchall()
        inserted = 0
        for r in rows:
            try:
                new.execute(
                    f"INSERT OR IGNORE INTO {tbl} ({col_list}) VALUES ({placeholders})",
                    tuple(r),
                )
                inserted += 1
            except sqlite3.IntegrityError as e:
                print(f"  [warn] {tbl}: {e}")
        print(f"  {tbl}: {inserted}/{len(rows)} rows copied from temp DB")

    # ═══════════════════════════════════════════════════════════════
    # Step 5: Recover tables from lost_and_found
    # ═══════════════════════════════════════════════════════════════

    # 5a: emotion_states (rootpgno=7, nfield=10, 14 rows)
    # c1=user_id, c2=ai_id, c3=energy, c4=pleasure, c5=arousal(→activation),
    # c6=longing, c7=dominance(→security), c8=created_at(→last_interaction_at), c9=updated_at
    print("[repair] Recovering emotion_states from lost_and_found ...")
    es_rows = recover.execute(
        "SELECT id, c1, c2, c3, c4, c5, c6, c7, c8, c9 "
        "FROM lost_and_found WHERE rootpgno=7"
    ).fetchall()
    inserted = 0
    for r in es_rows:
        try:
            new.execute(
                """INSERT OR IGNORE INTO emotion_states
                   (id, user_id, ai_id, energy, pleasure, activation,
                    longing, security, last_interaction_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                tuple(r),
            )
            inserted += 1
        except sqlite3.IntegrityError as e:
            print(f"  [warn] emotion_states: {e}")
    print(f"  -> {inserted}/{len(es_rows)} emotion_states recovered")

    # 5b: emotion_trigger_logs (rootpgno=8, nfield=5, 12 rows)
    # c1=user_id, c2=ai_id, c3=trigger_type, c4=triggered_at
    print("[repair] Recovering emotion_trigger_logs from lost_and_found ...")
    et_rows = recover.execute(
        "SELECT id, c1, c2, c3, c4 "
        "FROM lost_and_found WHERE rootpgno=8"
    ).fetchall()
    inserted = 0
    for r in et_rows:
        try:
            new.execute(
                """INSERT OR IGNORE INTO emotion_trigger_logs
                   (id, user_id, ai_id, trigger_type, triggered_at)
                   VALUES (?,?,?,?,?)""",
                tuple(r),
            )
            inserted += 1
        except sqlite3.IntegrityError as e:
            print(f"  [warn] emotion_trigger_logs: {e}")
    print(f"  -> {inserted}/{len(et_rows)} emotion_trigger_logs recovered")

    # 5c: relational_anchors (rootpgno=9, nfield=10, 16 rows)
    # c1=user_id, c2=ai_id, c3=anchor_type, c4=content, c5=strength(→severity),
    # c6=chroma_id(→vector_id), c7=source_message_id(→hit_count), c8=created_at, c9=updated_at
    print("[repair] Recovering relational_anchors from lost_and_found ...")
    ra_rows = recover.execute(
        "SELECT id, c1, c2, c3, c4, c5, c6, c7, c8, c9 "
        "FROM lost_and_found WHERE rootpgno=9"
    ).fetchall()
    inserted = 0
    for r in ra_rows:
        try:
            new.execute(
                """INSERT OR IGNORE INTO relational_anchors
                   (id, user_id, ai_id, anchor_type, content, severity,
                    vector_id, hit_count, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                tuple(r),
            )
            inserted += 1
        except sqlite3.IntegrityError as e:
            print(f"  [warn] relational_anchors: {e}")
    print(f"  -> {inserted}/{len(ra_rows)} relational_anchors recovered")

    # 5d: follows (rootpgno=17, nfield=4, 20 rows)
    # c1=user_id, c2=ai_id, c3=created_at
    print("[repair] Recovering follows from lost_and_found ...")
    fo_rows = recover.execute(
        "SELECT id, c1, c2, c3 "
        "FROM lost_and_found WHERE rootpgno=17"
    ).fetchall()
    inserted = 0
    for r in fo_rows:
        try:
            new.execute(
                """INSERT OR IGNORE INTO follows
                   (id, user_id, ai_id, created_at)
                   VALUES (?,?,?,?)""",
                tuple(r),
            )
            inserted += 1
        except sqlite3.IntegrityError as e:
            print(f"  [warn] follows: {e}")
    print(f"  -> {inserted}/{len(fo_rows)} follows recovered")

    # 5e: chat_messages (rootpgno=15, nfield=8, 23 rows) - best effort
    # Original schema column order: id, user_id, ai_id, role, content,
    #   delivered, created_at, then ALTER TABLE additions: message_type, event
    # lost_and_found tuple: c1=user_id, c2=ai_id, c3=role, c4=content,
    #   c5=delivered, c6=created_at, c7=message_type(?), but data varies
    # Skipping this - mapping is ambiguous and data is mostly early test messages.
    print("  chat_messages: skipped (ambiguous mapping, will regenerate)")

    # ═══════════════════════════════════════════════════════════════
    # Step 6: Apply updated persona prompts
    # ═══════════════════════════════════════════════════════════════
    from scripts.seed_personas import PERSONAS
    for p in PERSONAS:
        new.execute(
            "UPDATE ai_personas SET personality_prompt=? WHERE name=?",
            (p["personality_prompt"], p["name"]),
        )
    print("[repair] Updated persona prompts from seed_personas.py")

    # --- Commit and verify ---
    new.commit()

    print("\n=== Verification ===")
    for tbl in ["users", "ai_personas", "interactions", "posts", "stories",
                 "chat_messages", "chat_summaries", "emotion_trigger_logs",
                 "emotion_states", "relational_anchors", "follows"]:
        cnt = new.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl}: {cnt} rows")

    print("\n=== Data correctness check ===")
    for r in new.execute("SELECT id, email, nickname, gender, is_admin FROM users").fetchall():
        print(f"  users[{r[0]}]: {r[1]} | {r[2]} | gender={r[3]} | admin={r[4]}")
    print()
    for r in new.execute("SELECT id, name, profession, category, avatar_url FROM ai_personas").fetchall():
        print(f"  ai_personas[{r[0]}]: {r[1]} | {r[2]} | {r[3]} | avatar={r[4]}")
    print()
    for r in new.execute("SELECT id, user_id, ai_id, energy, longing FROM emotion_states LIMIT 3").fetchall():
        print(f"  emotion_states[{r[0]}]: u={r[1]} a={r[2]} energy={r[3]} longing={r[4]}")

    ic = new.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"\n  Integrity check: {ic}")

    temp.close()
    recover.close()
    new.close()
    print(f"\n[repair] Done. New DB: {new_db}")


if __name__ == "__main__":
    asyncio.run(repair())
