import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

# Load .env from backend directory
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


class Settings(BaseModel):
    APP_NAME: str = "SoulPulse"
    DATABASE_URL: str = "sqlite+aiosqlite:///./soulpulse.db"
    SECRET_KEY: str = _env("SECRET_KEY", "change-me-in-production-use-a-real-secret")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Alibaba Cloud - Model Studio (DashScope)
    DASHSCOPE_API_KEY: str = _env("DASHSCOPE_API_KEY")
    DASHSCOPE_CHAT_MODEL: str = _env("DASHSCOPE_CHAT_MODEL", "qwen-max")
    DASHSCOPE_CHARACTER_MODEL: str = _env("DASHSCOPE_CHARACTER_MODEL", "qwen2.5-role-play")
    DASHSCOPE_IMAGE_MODEL: str = _env("DASHSCOPE_IMAGE_MODEL", "wanx2.1-t2i-turbo")
    DASHSCOPE_VIDEO_MODEL: str = _env("DASHSCOPE_VIDEO_MODEL", "wanx-v1")
    DASHSCOPE_EMBEDDING_MODEL: str = _env("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")

    # ChromaDB (vector store for memories)
    CHROMA_DB_PATH: str = _env("CHROMA_DB_PATH", "./chroma_data")

    # Alibaba Cloud - OSS
    OSS_ACCESS_KEY_ID: str = _env("OSS_ACCESS_KEY_ID")
    OSS_ACCESS_KEY_SECRET: str = _env("OSS_ACCESS_KEY_SECRET")
    OSS_BUCKET_NAME: str = _env("OSS_BUCKET_NAME", "soulpulse-media")
    OSS_ENDPOINT: str = _env("OSS_ENDPOINT", "https://oss-cn-hangzhou.aliyuncs.com")

    # CORS allowed origins (comma-separated, "*" for dev)
    ALLOWED_ORIGINS: str = _env("ALLOWED_ORIGINS", "*")

    # Story expiration (hours)
    STORY_EXPIRATION_HOURS: int = int(_env("STORY_EXPIRATION_HOURS", "24"))


settings = Settings()
