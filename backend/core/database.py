"""
SoulPulse 数据库配置模块

本模块负责：
1. 创建异步数据库引擎
2. 定义声明式基类（Base）供所有模型继承
3. 提供数据库会话依赖注入
4. 初始化数据库表结构
5. 执行数据库迁移

使用异步 SQLAlchemy 配合 aiosqlite 驱动，
支持高并发的异步数据库操作。

数据库特性：
- WAL 模式：提高并发读写性能
- 自动迁移：检测并添加新列
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from core.config import settings

# ── 创建异步数据库引擎 ──────────────────────────────────────────
# echo=False 关闭 SQL 日志输出（生产环境）
engine = create_async_engine(settings.DATABASE_URL, echo=False)

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