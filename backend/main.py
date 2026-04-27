"""
SoulPulse 后端服务入口模块

本模块是 FastAPI 应用的主入口点，负责：
1. 初始化数据库连接和表结构
2. 配置 CORS 中间件
3. 注册所有 API 路由
4. 设置静态文件服务
5. 配置请求日志中间件

架构说明：
- 使用异步 SQLAlchemy 进行数据库操作
- 采用 lifespan 管理应用生命周期
- 所有路由按功能模块划分
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from core.database import init_db
from core.config import settings
# 导入所有模型以确保表结构创建（noqa: F401 表示忽略未使用警告）
from models.memory_entry import MemoryEntry  # noqa: F401 — 内存条目模型
from models.proactive_dm import ProactiveDM  # noqa: F401 — 主动私信模型
from models.story import Story  # noqa: F401 — 故事/快拍模型
from models.comment import Comment  # noqa: F401 — 评论模型
from models.emotion_state import EmotionState  # noqa: F401 — 情绪状态模型
from models.emotion_trigger_log import EmotionTriggerLog  # noqa: F401 — 情绪触发日志模型
from models.relational_anchor import RelationalAnchor  # noqa: F401 — 关系锚点模型
from models.chat_summary import ChatSummary  # noqa: F401 — 聊天摘要模型（需在 ChatMessage 之前导入）
from models.chat_message import ChatMessage  # noqa: F401 — 聊天消息模型
from models.user_like import UserLike  # noqa: F401 — 用户点赞模型
from models.notification import Notification  # noqa: F401 — 通知模型
from models.saved_post import SavedPost  # noqa: F401 — 收藏帖子模型
from models.story_view import StoryView  # noqa: F401 — 故事浏览记录模型
from models.follow import Follow  # noqa: F401 — 关注关系模型
# 导入所有 API 路由
from api.endpoints.auth import router as auth_router
from api.endpoints.feed import router as feed_router
from api.endpoints.chat import router as chat_router
from api.endpoints.generate import router as generate_router
from api.endpoints.ai_profile import router as ai_profile_router
from api.endpoints.notifications import router as notifications_router
from api.endpoints.admin import router as admin_router
from api.endpoints.interactions import router as interactions_router
from api.endpoints.fcm import router as fcm_router
from api.admin import admin_router as admin_v2_router

# ── 结构化日志配置 ──────────────────────────────────────────
# 配置日志格式：时间戳 [日志级别] 模块名: 消息内容
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("soulpulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器

    在应用启动时：
    - 初始化数据库连接
    - 创建所有数据表
    - 执行数据库迁移

    在应用关闭时：
    - 清理资源（当前无特殊清理逻辑）
    """
    # 启动阶段：创建数据库表结构
    await init_db()
    yield
    # 关闭阶段：无特殊清理操作


# ── 创建 FastAPI 应用实例 ──────────────────────────────────────────
app = FastAPI(
    title="SoulPulse API",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS 中间件配置 ──────────────────────────────────────────
# 允许 Flutter Web 和移动端跨域访问
# 配置说明：
# - allow_origins: 允许的源，生产环境应配置具体域名
# - allow_credentials: 允许携带认证信息（Cookie、Authorization 头）
# - allow_methods: 允许的 HTTP 方法
# - allow_headers: 允许的请求头
_origins = (
    ["*"] if settings.ALLOWED_ORIGINS == "*"
    else [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册 API 路由 ──────────────────────────────────────────
app.include_router(auth_router)           # 认证相关：登录、注册、Token 刷新
app.include_router(feed_router)           # 信息流：帖子列表、点赞、收藏
app.include_router(chat_router)           # 聊天：与 AI 角色对话
app.include_router(generate_router)       # 内容生成：图片、视频生成
app.include_router(ai_profile_router)     # AI 角色档案：角色信息、动态
app.include_router(notifications_router)  # 通知：系统通知、互动提醒
app.include_router(interactions_router)   # 互动关系：亲密度、关系摘要
app.include_router(fcm_router)             # FCM：设备推送 Token 管理
app.include_router(admin_router)          # 管理后台：内容审核、数据分析（旧版兼容）
app.include_router(admin_v2_router)       # SDC 管理后台 v2：完整 7 模块


# ── 请求日志中间件 ──────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    HTTP 请求日志中间件

    记录每个请求的方法、路径、响应状态码和处理时间（毫秒）
    用于性能监控和问题排查
    """
    import time
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


# ── 静态文件服务 ──────────────────────────────────────────
# 挂载静态文件目录，用于提供头像、帖子图片、故事媒体等资源
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def root():
    """
    根路径健康检查接口

    返回应用名称和运行状态，用于：
    - 服务健康检查
    - 负载均衡探测
    - 前端连接测试
    """
    return {"app": "SoulPulse", "status": "running"}