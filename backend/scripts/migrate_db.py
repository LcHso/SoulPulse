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

        # ── interactions (intimacy decay mechanism) ─────────────────────────────
        # last_interaction_at: 最后互动时间，用于判断是否触发衰减
        "ALTER TABLE interactions ADD COLUMN last_interaction_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
        # decay_started_at: 衰减开始时间，首次进入衰减时记录
        "ALTER TABLE interactions ADD COLUMN decay_started_at TIMESTAMP",
        # return_bonus_remaining: 回温加成剩余次数（0-3）
        "ALTER TABLE interactions ADD COLUMN return_bonus_remaining INTEGER NOT NULL DEFAULT 0",
        # is_decaying: 是否正在衰减中（BOOLEAN in SQLite is INTEGER）
        "ALTER TABLE interactions ADD COLUMN is_decaying BOOLEAN NOT NULL DEFAULT 0",
        # 为 is_decaying 创建索引，加速衰减任务的过滤查询
        "CREATE INDEX IF NOT EXISTS ix_interactions_is_decaying ON interactions(is_decaying)",

        # ── posts (Memory Echo feature) ──────────────────────────────────────
        # memory_echo_refs: 引用的记忆 ID 列表（JSON），默认空数组
        "ALTER TABLE posts ADD COLUMN memory_echo_refs JSON DEFAULT '[]'",
        # emotion_snapshot: 生成帖子时的 5D 情绪快照（JSON），nullable
        "ALTER TABLE posts ADD COLUMN emotion_snapshot JSON",
        # trigger_type: 触发类型（scheduled/happy_post/moody_story/memory_echo/gem_request）
        "ALTER TABLE posts ADD COLUMN trigger_type VARCHAR(20) DEFAULT 'scheduled'",

        # ── interactions (proactive DM system / 思念触发) ──────────────────────
        # last_proactive_dm_at: 上次发送主动 DM 的时间，用于冷却判断
        "ALTER TABLE interactions ADD COLUMN last_proactive_dm_at TIMESTAMP",
        # proactive_dm_count: 累计发送主动 DM 的次数
        "ALTER TABLE interactions ADD COLUMN proactive_dm_count INTEGER DEFAULT 0",

        # ── proactive_dm_logs (思念触发日志表) ──────────────────────────────────
        # 此表通过 SQLAlchemy create_all 自动创建，不需要手动 ALTER

        # ── comments (delayed reply mechanism / 评论延迟回复) ────────────────────
        # ai_seen: AI 是否已看到该评论（BOOLEAN in SQLite is INTEGER）
        "ALTER TABLE comments ADD COLUMN ai_seen BOOLEAN NOT NULL DEFAULT 0",
        # ai_seen_at: AI 看到评论的时间
        "ALTER TABLE comments ADD COLUMN ai_seen_at TIMESTAMP",
        # ai_reply_at: AI 计划回复的展示时间（前端据此轮询判断）
        "ALTER TABLE comments ADD COLUMN ai_reply_at TIMESTAMP",
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
            if "duplicate column" in msg or "already exists" in msg:
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
