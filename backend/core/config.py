"""
SoulPulse 应用配置模块

本模块定义了应用的所有配置项，包括：
1. 数据库连接配置
2. JWT 认证配置
3. 阿里云 DashScope API 配置（大模型、图片、视频生成）
4. 阿里云 OSS 对象存储配置
5. ChromaDB 向量数据库配置
6. Firebase 推送通知配置

配置来源：
- 环境变量（.env 文件）
- 默认值

使用方式：
    from core.config import settings
    api_key = settings.DASHSCOPE_API_KEY
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

# 从 backend 目录加载 .env 环境变量文件
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _env(key: str, default: str = "") -> str:
    """
    获取环境变量值的辅助函数

    Args:
        key: 环境变量名
        default: 默认值，当环境变量不存在时返回

    Returns:
        str: 环境变量值或默认值
    """
    return os.getenv(key, default)


class Settings(BaseModel):
    """
    SoulPulse 应用配置类

    所有配置项都通过 Pydantic 模型定义，支持类型验证和默认值。

    配置分类：
    - 基础配置：应用名称、数据库 URL、JWT 密钥
    - 阿里云 DashScope：大语言模型、图片生成、视频生成、向量嵌入
    - 阿里云 OSS：对象存储服务
    - 其他：CORS、故事过期时间、Firebase 推送
    """

    # ── 基础配置 ──────────────────────────────────────────
    APP_NAME: str = "SoulPulse"
    # 数据库连接 URL，使用异步 SQLite
    DATABASE_URL: str = "sqlite+aiosqlite:///./soulpulse.db"
    # JWT 令牌签名密钥（生产环境必须修改）
    SECRET_KEY: str = _env("SECRET_KEY", "change-me-in-production-use-a-real-secret")
    # JWT 加密算法
    ALGORITHM: str = "HS256"
    # 访问令牌过期时间（分钟），默认 24 小时
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # ── 阿里云 DashScope 配置（模型服务平台）──────────────────────────
    # DashScope API 密钥，用于访问阿里云 AI 服务
    DASHSCOPE_API_KEY: str = _env("DASHSCOPE_API_KEY")
    # 对话模型：用于 AI 角色对话
    DASHSCOPE_CHAT_MODEL: str = _env("DASHSCOPE_CHAT_MODEL", "qwen-max")
    # 角色扮演模型：用于沉浸式角色对话
    DASHSCOPE_CHARACTER_MODEL: str = _env("DASHSCOPE_CHARACTER_MODEL", "qwen-plus-character")
    # 图片生成模型：用于 AI 角色头像、帖子图片生成
    DASHSCOPE_IMAGE_MODEL: str = _env("DASHSCOPE_IMAGE_MODEL", "wan2.7-image-pro")
    # 视频生成模型：用于 AI 角色动态内容生成
    DASHSCOPE_VIDEO_MODEL: str = _env("DASHSCOPE_VIDEO_MODEL", "wanx-v1")
    # 文本嵌入模型：用于记忆向量化存储
    DASHSCOPE_EMBEDDING_MODEL: str = _env("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v3")

    # ── ChromaDB 配置（向量数据库，用于记忆存储）──────────────────────────
    CHROMA_DB_PATH: str = _env("CHROMA_DB_PATH", "./chroma_data")

    # ── 阿里云 OSS 配置（对象存储服务）──────────────────────────
    OSS_ACCESS_KEY_ID: str = _env("OSS_ACCESS_KEY_ID")
    OSS_ACCESS_KEY_SECRET: str = _env("OSS_ACCESS_KEY_SECRET")
    # OSS 存储桶名称
    OSS_BUCKET_NAME: str = _env("OSS_BUCKET_NAME", "soulpulse-media")
    # OSS 地域节点
    OSS_ENDPOINT: str = _env("OSS_ENDPOINT", "https://oss-cn-hangzhou.aliyuncs.com")

    # ── 公网访问配置 ──────────────────────────────────────────
    # 服务器公网 URL，用于将本地路径转为 DashScope 可访问的完整 URL
    PUBLIC_URL: str = _env("PUBLIC_URL", "http://123.57.227.61")

    # ── CORS 配置 ──────────────────────────────────────────
    # 允许的跨域来源，多个用逗号分隔，"*" 表示允许所有（仅开发环境）
    ALLOWED_ORIGINS: str = _env("ALLOWED_ORIGINS", "*")

    # ── 媒体生成开关 ──────────────────────────────────────────
    # 是否启用图片/视频生成功能（设为 False 可关闭所有生成，节省 API 费用）
    ENABLE_MEDIA_GENERATION: bool = _env("ENABLE_MEDIA_GENERATION", "true").lower() in ("true", "1", "yes")

    # ── 故事/快拍配置 ──────────────────────────────────────────
    # 故事过期时间（小时），过期后自动删除
    STORY_EXPIRATION_HOURS: int = int(_env("STORY_EXPIRATION_HOURS", "24"))

    # ── Firebase 推送通知配置（可选）──────────────────────────
    # Firebase 服务账号 JSON 文件路径
    FIREBASE_SERVICE_ACCOUNT_PATH: str = _env("FIREBASE_SERVICE_ACCOUNT_PATH", "")


# 创建全局配置实例
settings = Settings()