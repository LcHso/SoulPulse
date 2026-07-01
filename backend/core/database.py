"""
SoulPulse 数据库配置模块

本模块负责：
1. 创建异步数据库引擎
2. 定义声明式基类（Base）供所有模型继承
3. 提供数据库会话依赖注入
4. 初始化数据库表结构
5. 执行数据库迁移

支持双数据库引擎：
- SQLite + aiosqlite：本地开发
- PostgreSQL + asyncpg：生产环境

数据库特性：
- SQLite: WAL 模式提高并发性能
- PostgreSQL: 连接池配置优化高并发
- 自动迁移：检测并添加新列
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from core.config import settings


# ── 创建异步数据库引擎 ──────────────────────────────────────────
def _create_engine():
    """
    根据 DATABASE_URL 前缀创建对应的异步引擎。
    - PostgreSQL: 使用连接池配置（pool_size, max_overflow, pool_pre_ping, pool_recycle）
    - SQLite: 使用 check_same_thread=False 允许多线程访问
    """
    db_url = settings.DATABASE_URL

    if db_url.startswith("postgresql") or db_url.startswith("postgres"):
        # PostgreSQL engine with connection pool settings
        return create_async_engine(
            db_url,
            echo=False,
            pool_size=20,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
    else:
        # SQLite engine with thread-safety arg
        return create_async_engine(
            db_url,
            echo=False,
            connect_args={"check_same_thread": False},
        )


engine = _create_engine()

# 创建异步会话工厂
# class_=AsyncSession: 指定使用异步会话
# expire_on_commit=False: 提交后对象不过期，避免额外查询
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """
    SQLAlchemy 声明式基类

    所有 ORM 模型都应继承此类，用于：
    - 自动映射数据库表
    - 统一模型配置
    - 支持类型注解
    """
    pass


async def get_db() -> AsyncSession:
    """
    获取数据库会话的依赖注入函数

    用于 FastAPI 路由中的依赖注入：
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...

    使用 async with 确保会话正确关闭。
    Yield 会话对象供调用方使用。

    Yields:
        AsyncSession: 异步数据库会话
    """
    async with async_session() as session:
        yield session


async def init_db():
    """
    初始化数据库

    执行以下操作：
    1. 导入所有模型（触发表结构注册）
    2. 创建所有数据表
    3. 启用 WAL 模式（提高 SQLite 并发性能）
    4. 执行数据库迁移（添加新列）

    注意：模型导入放在函数内部以避免循环导入问题。
    """
    # 在函数内部导入模型，避免循环导入
    import models.user  # noqa: F401
    import models.ai_persona  # noqa: F401
    import models.post  # noqa: F401
    import models.story  # noqa: F401
    import models.comment  # noqa: F401
    import models.chat_message  # noqa: F401
    import models.interaction  # noqa: F401
    import models.emotion_state  # noqa: F401
    import models.memory_entry  # noqa: F401
    import models.notification  # noqa: F401
    import models.follow  # noqa: F401
    import models.user_like  # noqa: F401
    import models.saved_post  # noqa: F401
    import models.proactive_dm  # noqa: F401
    import models.relational_anchor  # noqa: F401
    import models.emotion_trigger_log  # noqa: F401
    import models.chat_summary  # noqa: F401
    import models.story_view  # noqa: F401
    # SDC admin models
    import models.admin_audit_log  # noqa: F401
    import models.api_usage_log  # noqa: F401
    import models.system_config  # noqa: F401
    import models.content_moderation_log  # noqa: F401
    import models.global_knowledge_entry  # noqa: F401
    import models.visual_dna_version  # noqa: F401
    import models.gacha_script  # noqa: F401
    import models.virtual_gift  # noqa: F401
    import models.gem_transaction  # noqa: F401
    import models.milestone_config  # noqa: F401
    # 动漫化视觉系统（Plan Task 8）
    import models.character_design  # noqa: F401
    import models.cg_illustration  # noqa: F401
    import models.user_cg_collection  # noqa: F401
    # 资产管线 (Plan Task 5)
    import models.asset_registry  # noqa: F401
    # 对话场景与互动剧情 (Plan Task 3)
    import models.chat_scene  # noqa: F401
    # 服装与场景系统 (Plan Task 2)
    import models.outfit_config  # noqa: F401
    # 世界观扩展 (Plan Task 1)
    import models.world_event  # noqa: F401
    import models.persona_relationship  # noqa: F401
    import models.character_arc  # noqa: F401
    # 商业化深化 (Plan Task 4)
    import models.subscription  # noqa: F401
    import models.event_campaign  # noqa: F401
    # 角色发布管线与轮换 (Plan Task 9.3-9.4)
    import models.character_launch  # noqa: F401
    # 主动 DM 系统（思念触发）
    import models.proactive_dm_log  # noqa: F401
    # 推送通知系统
    import models.notification_preference  # noqa: F401
    import models.user_device  # noqa: F401
    import models.notification_log  # noqa: F401

    # 创建所有数据表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── SQLite 性能优化配置 ──────────────────────────────────────────
    # WAL 模式：允许同时读写，提高并发性能
    # busy_timeout：设置锁等待超时（毫秒）
    if "sqlite" in settings.DATABASE_URL:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=5000"))

            # ── 数据库迁移：为 posts 表添加 status 列 ──────────────────────────────────────────
            # status 用于内容审核工作流：0=待审核, 1=已发布, 2=已拒绝
            try:
                await conn.execute(text("SELECT status FROM posts LIMIT 1"))
            except Exception:
                # 列不存在，执行迁移
                await conn.execute(text("ALTER TABLE posts ADD COLUMN status INTEGER DEFAULT 0"))
                print("[database] Added status column to posts table")

            # ── 数据库迁移：为 users 表添加 is_admin 列 ──────────────────────────────────────────
            # is_admin 用于标识管理员账户：0=普通用户, 1=管理员
            try:
                await conn.execute(text("SELECT is_admin FROM users LIMIT 1"))
            except Exception:
                # 列不存在，执行迁移
                await conn.execute(text("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0"))
                print("[database] Added is_admin column to users table")

            # ── 数据库迁移：为 posts 表添加 post_type 列 ──────────────────────────────────────────
            # post_type 用于标识帖子类型：image_only, video, carousel
            try:
                await conn.execute(text("SELECT post_type FROM posts LIMIT 1"))
            except Exception:
                await conn.execute(
                    text("ALTER TABLE posts ADD COLUMN post_type VARCHAR(50) DEFAULT 'image_only'")
                )
                print("[database] Added post_type column to posts table")

            # ── 数据库迁移：chat_messages 表添加多模态字段 ──────────────────────────────
            # 支持图片/语音/视频消息及 AI 语音回复
            chat_msg_migrations = {
                "media_type": "ALTER TABLE chat_messages ADD COLUMN media_type VARCHAR(20)",
                "media_url": "ALTER TABLE chat_messages ADD COLUMN media_url VARCHAR(500)",
                "media_metadata_json": "ALTER TABLE chat_messages ADD COLUMN media_metadata_json JSON",
                "voice_url": "ALTER TABLE chat_messages ADD COLUMN voice_url VARCHAR(500)",
            }
            for col, sql in chat_msg_migrations.items():
                try:
                    await conn.execute(text(f"SELECT {col} FROM chat_messages LIMIT 1"))
                except Exception:
                    await conn.execute(text(sql))
                    print(f"[database] Added {col} column to chat_messages table")

            # ── 数据库迁移：ai_personas 表添加 voice_config_json 列 ──────────────────────
            # 用于角色专属的 TTS 语音合成参数
            try:
                await conn.execute(text("SELECT voice_config_json FROM ai_personas LIMIT 1"))
            except Exception:
                await conn.execute(
                    text("ALTER TABLE ai_personas ADD COLUMN voice_config_json JSON")
                )
                print("[database] Added voice_config_json column to ai_personas table")

            # ── 数据库迁移：ai_personas 表添加世界观扩展字段 ───────────────────────
            # family_background / daily_routine_json / secret_layers_json / character_arc_id
            persona_world_migrations = {
                "family_background": "ALTER TABLE ai_personas ADD COLUMN family_background TEXT",
                "daily_routine_json": "ALTER TABLE ai_personas ADD COLUMN daily_routine_json JSON",
                "secret_layers_json": "ALTER TABLE ai_personas ADD COLUMN secret_layers_json JSON",
                "character_arc_id": "ALTER TABLE ai_personas ADD COLUMN character_arc_id INTEGER",
            }
            for col, sql in persona_world_migrations.items():
                try:
                    await conn.execute(text(f"SELECT {col} FROM ai_personas LIMIT 1"))
                except Exception:
                    await conn.execute(text(sql))
                    print(f"[database] Added {col} column to ai_personas table")

            # ── 数据库迁移：interactions 表添加留存机制字段 (Plan Task 6) ─────────────
            # streak_count / last_streak_date / ritual_config_json / total_interaction_days
            interaction_retention_migrations = {
                "streak_count": "ALTER TABLE interactions ADD COLUMN streak_count INTEGER DEFAULT 0",
                "last_streak_date": "ALTER TABLE interactions ADD COLUMN last_streak_date VARCHAR(10)",
                "ritual_config_json": "ALTER TABLE interactions ADD COLUMN ritual_config_json JSON",
                "total_interaction_days": "ALTER TABLE interactions ADD COLUMN total_interaction_days INTEGER DEFAULT 0",
            }
            for col, sql in interaction_retention_migrations.items():
                try:
                    await conn.execute(text(f"SELECT {col} FROM interactions LIMIT 1"))
                except Exception:
                    await conn.execute(text(sql))
                    print(f"[database] Added {col} column to interactions table")

            # ── 数据库迁移：interactions 表添加主动 DM 系统字段 ──────────────────
            # last_proactive_dm_at / proactive_dm_count
            interaction_proactive_dm_migrations = {
                "last_proactive_dm_at": "ALTER TABLE interactions ADD COLUMN last_proactive_dm_at TIMESTAMP",
                "proactive_dm_count": "ALTER TABLE interactions ADD COLUMN proactive_dm_count INTEGER DEFAULT 0",
            }
            for col, sql in interaction_proactive_dm_migrations.items():
                try:
                    await conn.execute(text(f"SELECT {col} FROM interactions LIMIT 1"))
                except Exception:
                    await conn.execute(text(sql))
                    print(f"[database] Added {col} column to interactions table")