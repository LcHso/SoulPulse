import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import init_db
from models.memory_entry import MemoryEntry  # noqa: F401 — ensure table creation
from models.proactive_dm import ProactiveDM  # noqa: F401 — ensure table creation
from models.story import Story  # noqa: F401 — ensure table creation
from models.comment import Comment  # noqa: F401 — ensure table creation
from api.endpoints.auth import router as auth_router
from api.endpoints.feed import router as feed_router
from api.endpoints.chat import router as chat_router
from api.endpoints.generate import router as generate_router
from api.endpoints.ai_profile import router as ai_profile_router


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(feed_router)
app.include_router(chat_router)
app.include_router(generate_router)
app.include_router(ai_profile_router)


@app.get("/")
async def root():
    return {"app": "SoulPulse", "status": "running"}
