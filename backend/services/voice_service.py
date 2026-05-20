"""
语音服务模块（Voice Service）

================================================================================
功能概述
================================================================================
基于阿里云 DashScope 的语音 API，为 SoulPulse 提供：
- ASR（自动语音识别）：将用户的语音消息转录为文本（Paraformer-v2）
- TTS（语音合成）：将 AI 角色的文字回复合成为音频（CosyVoice-v1）
- 缓存的预录问候语：减少高频场景的 API 调用

API 参考：
- ASR: POST https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription
       Model: paraformer-v2（异步任务，需轮询 task 状态）
- TTS: POST https://dashscope.aliyuncs.com/api/v1/services/audio/tts/synthesis
       Model: cosyvoice-v1（直接返回音频流）

合成的音频文件保存到 backend/static/voice/，通过 /static/voice/* URL 提供访问。

================================================================================
使用示例
================================================================================
    from services.voice_service import voice_service

    # 转录用户语音
    result = await voice_service.transcribe_audio("https://example.com/voice.wav")
    text = result["text"]

    # 生成 AI 语音回复
    voice_url = await voice_service.generate_voice(
        text="你好，今天过得怎么样？",
        voice_config={"voice_id": "longxiaochun", "speed": 1.0},
    )
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from pathlib import Path

import httpx

from core.config import settings

logger = logging.getLogger(__name__)

# DashScope API 端点
_ASR_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
_ASR_TASK_URL_TEMPLATE = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"
_TTS_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/synthesis"

# 模型名称
_ASR_MODEL = "paraformer-v2"
_TTS_MODEL = "cosyvoice-v1"

# 输出目录（FastAPI 已挂载在 /static）
_VOICE_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "static" / "voice"
_VOICE_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 默认 voice_id（CosyVoice 内置音色之一）
_DEFAULT_VOICE_ID = "longxiaochun"

# 轮询配置
_ASR_POLL_INTERVAL_SEC = 1.5
_ASR_POLL_TIMEOUT_SEC = 60.0


def _absolute_audio_url(audio_url: str) -> str:
    """将相对音频路径转为公网可访问的 URL。"""
    if not audio_url:
        return audio_url
    if audio_url.startswith(("http://", "https://")):
        return audio_url
    base = settings.PUBLIC_URL.rstrip("/")
    if not audio_url.startswith("/"):
        audio_url = "/" + audio_url
    return f"{base}{audio_url}"


class VoiceService:
    """
    语音消息处理服务。

    封装了阿里云 DashScope 的 ASR（语音转文字）和 TTS（文字转语音）能力，
    供聊天服务调用以处理多模态语音交互。
    """

    # ── ASR：用户语音 → 文本 ──────────────────────────────────

    async def transcribe_audio(self, audio_url: str) -> dict:
        """
        将用户的语音消息转录为文本。

        Paraformer ASR 是异步任务模式：先提交任务获取 task_id，
        然后轮询任务状态直到 SUCCEEDED 或 FAILED。

        Args:
            audio_url: 用户上传的音频文件 URL

        Returns:
            dict: {"text": str, "duration": float, "language": str}
                  失败时 text 为空字符串
        """
        full_url = _absolute_audio_url(audio_url)
        api_key = settings.DASHSCOPE_API_KEY

        if not api_key:
            logger.warning("DASHSCOPE_API_KEY not configured; skipping ASR")
            return {"text": "", "duration": 0.0, "language": "zh"}

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        submit_body = {
            "model": _ASR_MODEL,
            "input": {"file_urls": [full_url]},
            "parameters": {"language_hints": ["zh", "en"]},
        }

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 1. 提交任务
                submit_resp = await client.post(
                    _ASR_SUBMIT_URL, headers=headers, json=submit_body,
                )
                submit_resp.raise_for_status()
                submit_data = submit_resp.json()
                task_id = submit_data.get("output", {}).get("task_id")
                if not task_id:
                    logger.warning("ASR submit returned no task_id: %s", submit_data)
                    return {"text": "", "duration": 0.0, "language": "zh"}

                # 2. 轮询任务状态
                poll_url = _ASR_TASK_URL_TEMPLATE.format(task_id=task_id)
                poll_headers = {"Authorization": f"Bearer {api_key}"}

                deadline = time.time() + _ASR_POLL_TIMEOUT_SEC
                while time.time() < deadline:
                    await asyncio.sleep(_ASR_POLL_INTERVAL_SEC)
                    poll_resp = await client.get(poll_url, headers=poll_headers)
                    poll_resp.raise_for_status()
                    poll_data = poll_resp.json()
                    output = poll_data.get("output", {})
                    status = output.get("task_status")

                    if status == "SUCCEEDED":
                        return self._parse_asr_result(output)
                    if status in ("FAILED", "CANCELED"):
                        logger.warning("ASR task failed: %s", output)
                        return {"text": "", "duration": 0.0, "language": "zh"}

                logger.warning("ASR task %s timed out", task_id)
                return {"text": "", "duration": 0.0, "language": "zh"}

        except Exception as e:
            logger.warning("ASR transcribe_audio failed (url=%s): %s", full_url, e)
            return {"text": "", "duration": 0.0, "language": "zh"}
        finally:
            latency_ms = int((time.time() - start) * 1000)
            logger.debug("ASR transcribe_audio latency=%dms", latency_ms)

    @staticmethod
    def _parse_asr_result(output: dict) -> dict:
        """从 ASR 任务输出中提取转录文本和元数据。"""
        try:
            results = output.get("results", []) or []
            if not results:
                return {"text": "", "duration": 0.0, "language": "zh"}
            first = results[0]
            transcription_url = first.get("transcription_url")
            duration = float(first.get("duration", 0.0) or 0.0)

            # 如果是 URL 形式，需要再下载（v2 通常直接返回 sentences）
            sentences = first.get("transcripts") or first.get("sentences") or []
            text_parts: list[str] = []
            for s in sentences:
                if isinstance(s, dict):
                    text_parts.append(s.get("text", ""))
                else:
                    text_parts.append(str(s))
            text = "".join(text_parts).strip()

            # 兜底：直接的 text 字段
            if not text:
                text = (first.get("text") or "").strip()

            return {
                "text": text,
                "duration": duration,
                "language": first.get("language", "zh"),
                "transcription_url": transcription_url,
            }
        except Exception as e:
            logger.warning("Failed to parse ASR result: %s", e)
            return {"text": "", "duration": 0.0, "language": "zh"}

    # ── TTS：AI 文本 → 语音 ───────────────────────────────────

    async def generate_voice(
        self,
        text: str,
        voice_config: dict | None,
        persona_id: int | None = None,
    ) -> str | None:
        """
        将 AI 角色的回复文本合成为语音文件。

        Args:
            text: 待合成的文本
            voice_config: 角色语音配置（voice_id/speed/pitch 等）
            persona_id: 角色 ID（用于生成文件名）

        Returns:
            str | None: 生成的音频 URL（相对路径，如 /static/voice/xxx.mp3）；
                       失败返回 None
        """
        if not text or not text.strip():
            return None

        api_key = settings.DASHSCOPE_API_KEY
        if not api_key:
            logger.warning("DASHSCOPE_API_KEY not configured; skipping TTS")
            return None

        cfg = voice_config or {}
        voice_id = cfg.get("voice_id") or _DEFAULT_VOICE_ID
        speed = float(cfg.get("speed", 1.0))
        pitch = float(cfg.get("pitch", 1.0))

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # CosyVoice 同步语音合成请求体
        body = {
            "model": _TTS_MODEL,
            "input": {"text": text},
            "parameters": {
                "voice": voice_id,
                "rate": speed,
                "pitch": pitch,
                "format": "mp3",
                "sample_rate": 22050,
            },
        }

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(_TTS_URL, headers=headers, json=body)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")

                # 直接返回二进制音频
                if "audio" in content_type or content_type.startswith("application/octet-stream"):
                    audio_bytes = resp.content
                else:
                    # 返回 JSON，可能包含 audio_url 或 base64 数据
                    data = resp.json()
                    audio_bytes = await self._extract_audio_bytes(client, data)
                    if not audio_bytes:
                        logger.warning("TTS returned no audio data: %s", data)
                        return None

                # 保存为本地文件
                ts = int(time.time())
                pid = persona_id if persona_id is not None else "x"
                fname = f"{pid}_{ts}_{uuid.uuid4().hex[:8]}.mp3"
                fpath = _VOICE_OUTPUT_DIR / fname
                with open(fpath, "wb") as f:
                    f.write(audio_bytes)

                rel_url = f"/static/voice/{fname}"
                return rel_url

        except Exception as e:
            logger.warning("TTS generate_voice failed: %s", e)
            return None
        finally:
            latency_ms = int((time.time() - start) * 1000)
            logger.debug("TTS generate_voice latency=%dms", latency_ms)

    @staticmethod
    async def _extract_audio_bytes(client: httpx.AsyncClient, data: dict) -> bytes | None:
        """从 TTS JSON 响应中提取音频字节（支持 URL 或 base64）。"""
        import base64

        output = data.get("output", {}) if isinstance(data, dict) else {}
        # URL 形式
        url = output.get("audio_url") or output.get("url")
        if url:
            try:
                r = await client.get(url)
                r.raise_for_status()
                return r.content
            except Exception as e:
                logger.warning("TTS audio download failed: %s", e)
                return None
        # base64 形式
        b64 = output.get("audio") or output.get("audio_base64")
        if b64:
            try:
                return base64.b64decode(b64)
            except Exception as e:
                logger.warning("TTS audio base64 decode failed: %s", e)
                return None
        return None

    # ── 预缓存问候语 ───────────────────────────────────────

    async def get_cached_greeting(
        self,
        persona_id: int,
        greeting_type: str,
    ) -> str | None:
        """
        查询是否存在预缓存的角色问候语音频。

        约定的缓存路径：
            backend/static/voice/cache/{persona_id}/{greeting_type}.mp3

        Args:
            persona_id: AI 角色 ID
            greeting_type: 问候类型（如 "welcome" / "morning" / "night"）

        Returns:
            str | None: 缓存音频的相对 URL；不存在则返回 None
        """
        cache_dir = _VOICE_OUTPUT_DIR / "cache" / str(persona_id)
        cache_file = cache_dir / f"{greeting_type}.mp3"
        if cache_file.exists():
            return f"/static/voice/cache/{persona_id}/{greeting_type}.mp3"
        return None


# 模块级单例
voice_service = VoiceService()
