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
from models.memory_entry import MemoryEntry  # noqa: F401 — ensure table creation
from models.proactive_dm import ProactiveDM  # noqa: F401 — ensure table creation
from models.story import Story  # noqa: F401 — ensure table creation
from models.comment import Comment  # noqa: F401 — ensure table creation
from models.emotion_state import EmotionState  # noqa: F401 — ensure table creation
from models.emotion_trigger_log import EmotionTriggerLog  # noqa: F401 — ensure table creation
from models.relational_anchor import RelationalAnchor  # noqa: F401 — ensure table creation
from models.chat_summary import ChatSummary  # noqa: F401 — ensure table creation (before ChatMessage)
from models.chat_message import ChatMessage  # noqa: F401 — ensure table creation
from models.user_like import UserLike  # noqa: F401
from models.notification import Notification  # noqa: F401
from models.saved_post import SavedPost  # noqa: F401
from models.story_view import StoryView  # noqa: F401
from models.follow import Follow  # noqa: F401
from api.endpoints.auth import router as auth_router
from api.endpoints.feed import router as feed_router
from api.endpoints.chat import router as chat_router
from api.endpoints.generate import router as generate_router
from api.endpoints.ai_profile import router as ai_profile_router
from api.endpoints.notifications import router as notifications_router

# ── Structured Logging ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("soulpulse")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    await init_db()
    yield
    # Shutdown: nothing special


app = FastAPI(
    title="SoulPulse API",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS - allow Flutter web & mobile to connect
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

app.include_router(auth_router)
app.include_router(feed_router)
app.include_router(chat_router)
app.include_router(generate_router)
app.include_router(ai_profile_router)
app.include_router(notifications_router)


# ── Request logging middleware ──────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start) * 1000
    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


# Mount static files for avatars, posts, stories
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


@app.get("/")
async def root():
    return {"app": "SoulPulse", "status": "running"}
