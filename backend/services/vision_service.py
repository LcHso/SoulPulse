"""
视觉理解服务模块（Vision Service）

================================================================================
功能概述
================================================================================
基于阿里云 DashScope 的 Qwen-VL 多模态大模型，为 SoulPulse 的 AI 角色
提供图片理解能力。当用户在聊天中发送图片时，AI 角色会根据自己的人格设定
生成符合性格的情绪化反应（而非冷冰冰的客观描述）。

核心能力：
- analyze_image(): 角色化图片反应（in-character emotional reaction）
- describe_image_for_context(): 中性事实描述（用于记忆/上下文存储）

API 参考：
- 模型: qwen-vl-max（多模态视觉模型）
- 接口: https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
- 消息格式: messages[].content 为数组，包含 {type:"text"} 和 {type:"image_url"}

================================================================================
使用示例
================================================================================
    from services.vision_service import vision_service

    reaction = await vision_service.analyze_image(
        image_url="https://example.com/photo.jpg",
        persona_name="陆晨曦",
        persona_prompt="一个温柔的医生……",
        context="用户最近心情不好",
    )
"""
from __future__ import annotations

import logging
import time

from openai import AsyncOpenAI

from core.config import settings

logger = logging.getLogger(__name__)

# Qwen-VL 多模态模型名称
_VL_MODEL = "qwen-vl-max"

# OpenAI 兼容客户端单例（懒加载）
_vl_client: AsyncOpenAI | None = None


def _get_vl_client() -> AsyncOpenAI:
    """获取 Qwen-VL 客户端（懒加载）。"""
    global _vl_client
    if _vl_client is None:
        _vl_client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _vl_client


def _absolute_image_url(image_url: str) -> str:
    """
    将相对路径转为完整的公网可访问 URL。

    DashScope API 需要公网可访问的图片 URL，本地相对路径需要
    拼接 PUBLIC_URL 前缀。
    """
    if not image_url:
        return image_url
    if image_url.startswith(("http://", "https://", "data:")):
        return image_url
    base = settings.PUBLIC_URL.rstrip("/")
    if not image_url.startswith("/"):
        image_url = "/" + image_url
    return f"{base}{image_url}"


class VisionService:
    """
    图片理解服务。

    使用 Qwen-VL 多模态模型分析用户发送的图片，并基于角色人格
    生成情绪化的反应或中性的事实描述。
    """

    async def analyze_image(
        self,
        image_url: str,
        persona_name: str,
        persona_prompt: str,
        context: str = "",
    ) -> str:
        """
        分析用户发送的图片并生成符合角色人格的反应。

        Args:
            image_url: 图片 URL（相对路径或绝对 URL）
            persona_name: AI 角色名称
            persona_prompt: 角色性格 prompt
            context: 最近对话上下文（可选）

        Returns:
            str: 角色对图片的情绪化反应文本
        """
        full_url = _absolute_image_url(image_url)

        # 系统提示词：强调情绪化、角色化反应
        system_prompt = (
            f"You are {persona_name}, a real person. Your character profile:\n"
            f"{persona_prompt[:600]}\n\n"
            "The user just sent you an image in your private chat. "
            "React EMOTIONALLY and IN-CHARACTER, NOT clinically. "
            "Do NOT describe the image like a captioner or AI. "
            "Instead, react like a real human would in chat — with surprise, "
            "warmth, curiosity, teasing, concern, etc., as fits your personality.\n"
            "Keep replies short and natural (1-3 sentences). "
            "You may use full-width parentheses（）to convey actions/expressions, "
            "matching your usual texting style.\n"
            "Never mention that you are an AI or analyzing pixels."
        )
        if context:
            system_prompt += f"\n\nRecent conversation context:\n{context[:400]}"

        user_content = [
            {"type": "image_url", "image_url": {"url": full_url}},
            {"type": "text", "text": "（用户发了一张图给你）"},
        ]

        client = _get_vl_client()
        start = time.time()
        try:
            response = await client.chat.completions.create(
                model=_VL_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.85,
                max_tokens=300,
            )
            content = response.choices[0].message.content
            return (content or "").strip()
        except Exception as e:
            logger.warning(
                "Vision analyze_image failed (url=%s): %s",
                full_url, e,
            )
            return "（看了看你发来的图）嗯……我看到了。"
        finally:
            latency_ms = int((time.time() - start) * 1000)
            logger.debug("Vision analyze_image latency=%dms", latency_ms)

    async def describe_image_for_context(self, image_url: str) -> str:
        """
        生成图片的简短事实性描述，用于记忆/上下文存储。

        与 analyze_image 不同，此方法返回中性、客观的描述文本，
        适合作为长期记忆的输入。

        Args:
            image_url: 图片 URL

        Returns:
            str: 图片的简短事实描述（≤80 字）
        """
        full_url = _absolute_image_url(image_url)
        client = _get_vl_client()

        try:
            response = await client.chat.completions.create(
                model=_VL_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an image description assistant. "
                            "Describe the given image in one neutral, factual sentence "
                            "(under 80 Chinese characters). Focus on the main subject, "
                            "setting, and notable visual elements. No emotional language."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": full_url}},
                            {"type": "text", "text": "请描述这张图。"},
                        ],
                    },
                ],
                temperature=0.3,
                max_tokens=120,
            )
            content = response.choices[0].message.content
            return (content or "").strip()
        except Exception as e:
            logger.warning(
                "Vision describe_image_for_context failed (url=%s): %s",
                full_url, e,
            )
            return "用户发送的一张图片"


# 模块级单例
vision_service = VisionService()
