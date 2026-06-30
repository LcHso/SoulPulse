"""
Database migration script - adds missing columns from the optimization sprint.
Non-destructive (ADD COLUMN only). Safe to re-run multiple times.

Missing columns identified by audit:
  interactions:   active_scene_id
  gacha_scripts:  preview_cg_url, completion_reward_json, difficulty_rating,
                  estimated_duration, has_multiple_endings
  virtual_gifts:  reaction_template, triggers_scene, combo_bonus_threshold
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "soulpulse.db")
    print(f"Connecting to: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    migrations = [
        # ── interactions ─────────────────────────────────────────────────────
        # active_scene_id: FK to chat_scenes, nullable (no FK constraint in SQLite ALTER)
        "ALTER TABLE interactions ADD COLUMN active_scene_id INTEGER REFERENCES chat_scenes(id)",

        # ── gacha_scripts ────────────────────────────────────────────────────
        "ALTER TABLE gacha_scripts ADD COLUMN preview_cg_url VARCHAR(500)",
        "ALTER TABLE gacha_scripts ADD COLUMN completion_reward_json JSON",
        "ALTER TABLE gacha_scripts ADD COLUMN difficulty_rating INTEGER",
        "ALTER TABLE gacha_scripts ADD COLUMN estimated_duration VARCHAR(50)",
        # BOOLEAN in SQLite is INTEGER; default FALSE = 0
        "ALTER TABLE gacha_scripts ADD COLUMN has_multiple_endings BOOLEAN NOT NULL DEFAULT 0",

        # ── virtual_gifts ────────────────────────────────────────────────────
        "ALTER TABLE virtual_gifts ADD COLUMN reaction_template TEXT",
        # BOOLEAN default FALSE = 0
        "ALTER TABLE virtual_gifts ADD COLUMN triggers_scene BOOLEAN NOT NULL DEFAULT 0",
        "ALTER TABLE virtual_gifts ADD COLUMN combo_bonus_threshold INTEGER",

        # ── ai_personas ──────────────────────────────────────────────────────
        # SillyTavern V2 character card JSON for import/export
        "ALTER TABLE ai_personas ADD COLUMN tavern_card_json TEXT",
        # creator_user_id: FK to users, nullable (NULL = global/official persona)
        "ALTER TABLE ai_personas ADD COLUMN creator_user_id INTEGER REFERENCES users(id)",
        "CREATE INDEX IF NOT EXISTS ix_ai_personas_creator_user_id ON ai_personas(creator_user_id)",
        # persona_type / feature_tier / is_public for character classification & feature gating
        "ALTER TABLE ai_personas ADD COLUMN persona_type VARCHAR(20) DEFAULT 'official'",
        "CREATE INDEX IF NOT EXISTS ix_ai_personas_persona_type ON ai_personas(persona_type)",
        "ALTER TABLE ai_personas ADD COLUMN feature_tier VARCHAR(20) DEFAULT 'full'",
        "ALTER TABLE ai_personas ADD COLUMN is_public BOOLEAN DEFAULT 0",
    ]

    success = 0
    skipped = 0
    errors = 0

    for sql in migrations:
        try:
            cursor.execute(sql)
            print(f"  OK: {sql}")
            success += 1
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "duplicate column" in msg:
                print(f"  SKIP (already exists): {sql[:80]}")
                skipped += 1
            else:
                print(f"  ERROR: {e} -- {sql}")
                errors += 1

    conn.commit()
    conn.close()

    print(f"\nMigration complete! success={success}, skipped={skipped}, errors={errors}")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    migrate()
