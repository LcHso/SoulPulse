"""
SoulPulse 图片生成服务模块

基于阿里云 DashScope 万象模型的图片生成服务。
支持 wan2.6+ 新版 API 和旧版 API (text2image)。

wan2.6+ 官方端点规范:
  - 同步: POST /services/aigc/multimodal-generation/generation
  - 异步: POST /services/aigc/image-generation/generation (Header: X-DashScope-Async: enable)
  - 任务查询: GET /tasks/{task_id}

旧版 (wan2.5 及以下):
  - 仅异步: POST /services/aigc/text2image/image-synthesis (Header: X-DashScope-Async: enable)

参考文档:
  - 万相-文生图 V2 API: https://help.aliyun.com/zh/model-studio/text-to-image-v2-api-reference
  - 万相-图像生成与编辑 API: https://help.aliyun.com/zh/model-studio/wan-image-generation-api-reference
"""

import asyncio
import hashlib
import random
import uuid
from pathlib import Path

import httpx

from core.config import settings

# ── 图像尺寸配置 ──────────────────────────────────────────
# 加权随机选择：40% 9:16 竖版，30% 1:1 方形，30% 16:9 横版
ASPECT_RATIOS = [
    ("720*1280", 0.40),   # 9:16 portrait
    ("1024*1024", 0.30),  # 1:1 square
    ("1280*720", 0.30),   # 16:9 landscape
]


def _get_random_size() -> str:
    """根据权重随机选择图像尺寸。"""
    sizes = [size for size, _ in ASPECT_RATIOS]
    weights = [weight for _, weight in ASPECT_RATIOS]
    return random.choices(sizes, weights=weights, k=1)[0]

# ── DashScope API 端点 ──────────────────────────────────────────
_BASE = "https://dashscope.aliyuncs.com/api/v1"

# wan2.6+ 同步端点
_URL_SYNC = f"{_BASE}/services/aigc/multimodal-generation/generation"
# wan2.6+ 异步端点 (与同步端点不同!)
_URL_ASYNC_NEW = f"{_BASE}/services/aigc/image-generation/generation"
# 旧版异步端点 (wan2.5 及以下)
_URL_ASYNC_LEGACY = f"{_BASE}/services/aigc/text2image/image-synthesis"
# 异步任务查询端点
_URL_TASK = f"{_BASE}/tasks/{{task_id}}"

# 使用新版 API 的模型前缀
_NEW_API_PREFIXES = ("wan2.6", "wan2.7", "wan2.8", "wan2.9", "wan3")

# 本地静态文件存储目录
_STATIC_DIR = Path(__file__).parent.parent / "static" / "posts"

# ── 强制质量保护 ──────────────────────────────────────────
ENFORCED_NEGATIVE_PROMPT = (
    "low quality, blurry, deformed, ugly, bad anatomy, bad hands, extra fingers, "
    "missing fingers, extra limbs, disfigured, poorly drawn face, mutation, "
    "worst quality, watermark, text, signature, pure anime style, cartoon, "
    "3d render, pure photorealistic, uncanny valley, overexposed, underexposed"
)

QUALITY_SUFFIX = (
    "semi-realistic digital art, stylized beauty, soft cinematic lighting, "
    "f/1.8 lens bokeh, high-end character illustration, professional color grading, "
    "detailed and refined, warm atmospheric tones, premium art quality"
)

DEFAULT_NEGATIVE_PROMPT = ENFORCED_NEGATIVE_PROMPT

# ── 内部工具函数 ──────────────────────────────────────────


def _is_new_api(model: str) -> bool:
    return any(model.startswith(p) for p in _NEW_API_PREFIXES)


def _get_persona_seed(persona_id: int) -> int:
    hex_hash = hashlib.md5(f"persona_{persona_id}".encode()).hexdigest()[:8]
    return int(hex_hash, 16) % 2147483647


def _auth_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
    }


def _resolve_public_url(path: str) -> str:
    """Convert a local path like /static/posts/xxx.png to a full public URL."""
    if path.startswith(("http://", "https://")):
        return path
    return f"{settings.PUBLIC_URL.rstrip('/')}{path}"


def _extract_image_urls(data: dict) -> list[str]:
    """从新版 (choices) 或旧版 (results) 响应格式中提取图片 URL。"""
    output = data.get("output", {})

    # 新版: output.choices[].message.content[].image
    for choice in output.get("choices", []):
        content = choice.get("message", {}).get("content", [])
        urls = [
            item["image"]
            for item in content
            if isinstance(item, dict) and "image" in item
        ]
        if urls:
            return urls

    # 旧版: output.results[].url
    results = output.get("results", [])
    if results:
        return [r["url"] for r in results if r.get("url")]

    return []


# ── 请求提交与轮询 ──────────────────────────────────────────


async def _call_sync(url: str, payload: dict) -> list[str]:
    """wan2.6+ 同步调用: 单次 POST 等待结果返回。"""
    headers = _auth_headers()
    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    urls = _extract_image_urls(data)
    if urls:
        return urls
    raise RuntimeError(f"No images in sync response: {data}")


async def _call_async(url: str, payload: dict) -> list[str]:
    """异步调用: POST 创建任务 → 轮询直到完成。"""
    headers = _auth_headers()
    headers["X-DashScope-Async"] = "enable"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        task_id = data.get("output", {}).get("task_id")
        if not task_id:
            # 某些情况下即使走异步端点也可能直接返回结果
            urls = _extract_image_urls(data)
            if urls:
                return urls
            raise RuntimeError(f"No task_id or images in response: {data}")

        poll_url = _URL_TASK.format(task_id=task_id)
        poll_headers = {"Authorization": f"Bearer {settings.DASHSCOPE_API_KEY}"}

        for _ in range(60):
            await asyncio.sleep(5)
            poll_resp = await client.get(poll_url, headers=poll_headers)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            status = poll_data.get("output", {}).get("task_status")
            if status == "SUCCEEDED":
                urls = _extract_image_urls(poll_data)
                if urls:
                    return urls
                raise RuntimeError(f"Task succeeded but no images: {poll_data}")
            elif status in ("FAILED", "UNKNOWN"):
                msg = poll_data.get("output", {}).get("message", "Unknown error")
                raise RuntimeError(f"Image generation failed: {msg}")

    raise TimeoutError("Image generation timeout (5 min)")


async def _generate(payload: dict, model: str) -> list[str]:
    """根据模型版本选择正确的端点和调用方式。"""
    if _is_new_api(model):
        # wan2.6+ 优先使用异步端点 (不阻塞连接, 更可靠)
        # 异步端点: image-generation/generation
        try:
            return await _call_async(_URL_ASYNC_NEW, payload)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                # 降级到同步端点
                return await _call_sync(_URL_SYNC, payload)
            raise
    else:
        # 旧版仅支持异步
        return await _call_async(_URL_ASYNC_LEGACY, payload)


# ── 公开 API ──────────────────────────────────────────


async def generate_image(
    prompt: str,
    size: str | None = None,
    n: int = 1,
    persona_id: int | None = None,
    negative_prompt: str | None = None,
) -> list[str]:
    """从文本提示生成图片。自动根据模型名选择 API 格式。

    Args:
        prompt: 图像生成提示词
        size: 图像尺寸（如 "720*1280"），为 None 时随机选择
        n: 生成数量
        persona_id: 角色ID（用于种子一致性）
        negative_prompt: 负面提示词

    Returns:
        list[str]: 生成的图像URL列表
    """
    if not settings.ENABLE_MEDIA_GENERATION:
        print("[image-gen] Media generation disabled, skipping")
        return []

    # 如果未指定尺寸，随机选择
    if size is None:
        size = _get_random_size()
        print(f"[image-gen] Randomly selected size: {size}")

    full_prompt = f"{prompt}, {QUALITY_SUFFIX}"
    model = settings.DASHSCOPE_IMAGE_MODEL
    neg = negative_prompt or ENFORCED_NEGATIVE_PROMPT

    if _is_new_api(model):
        parameters: dict = {
            "size": size,
            "n": n,
            "negative_prompt": neg,
            "prompt_extend": False,
            "watermark": False,
        }
        if persona_id is not None:
            parameters["seed"] = _get_persona_seed(persona_id)

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"text": full_prompt}]}
                ]
            },
            "parameters": parameters,
        }
    else:
        parameters = {"size": size, "n": n, "negative_prompt": neg}
        if persona_id is not None:
            parameters["seed"] = _get_persona_seed(persona_id)

        payload = {
            "model": model,
            "input": {"prompt": full_prompt},
            "parameters": parameters,
        }

    return await _generate(payload, model)


async def generate_image_with_face_ref(
    prompt: str,
    face_ref_url: str,
    size: str | None = None,
    n: int = 1,
    persona_id: int | None = None,
    negative_prompt: str | None = None,
) -> list[str]:
    """带面部参考的图片生成, 保持角色视觉一致性。

    wan2.6+: 在 content 数组中传入参考图 + enable_interleave=false (图像编辑模式)
    旧版: 使用 ref_image + ref_mode 参数

    Args:
        prompt: 图像生成提示词
        face_ref_url: 面部参考图像URL
        size: 图像尺寸（如 "720*1280"），为 None 时随机选择
        n: 生成数量
        persona_id: 角色ID（用于种子一致性）
        negative_prompt: 负面提示词

    Returns:
        list[str]: 生成的图像URL列表
    """
    if not settings.ENABLE_MEDIA_GENERATION:
        print("[image-gen] Media generation disabled, skipping")
        return []

    # 如果未指定尺寸，随机选择
    if size is None:
        size = _get_random_size()
        print(f"[image-gen] Randomly selected size: {size}")

    full_prompt = f"{prompt}, {QUALITY_SUFFIX}"
    model = settings.DASHSCOPE_IMAGE_MODEL
    neg = negative_prompt or ENFORCED_NEGATIVE_PROMPT
    resolved_face_url = _resolve_public_url(face_ref_url)

    if _is_new_api(model):
        parameters: dict = {
            "size": size,
            "n": n,
            "negative_prompt": neg,
            "prompt_extend": False,
            "watermark": False,
            "enable_interleave": False,
        }
        if persona_id is not None:
            parameters["seed"] = _get_persona_seed(persona_id)

        payload = {
            "model": model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": full_prompt},
                            {"image": resolved_face_url},
                        ],
                    }
                ]
            },
            "parameters": parameters,
        }
    else:
        parameters = {"size": size, "n": n, "negative_prompt": neg}
        if persona_id is not None:
            parameters["seed"] = _get_persona_seed(persona_id)

        payload = {
            "model": model,
            "input": {
                "prompt": full_prompt,
                "ref_image": resolved_face_url,
                "ref_mode": "face_ref",
                "ref_strength": 0.8,
            },
            "parameters": parameters,
        }

    return await _generate(payload, model)


async def generate_base_portrait(
    visual_prompt_tags: str,
    gender: str = "male",
    style: str = "photorealistic",
) -> str:
    """生成基础肖像图, 用于角色视觉一致性系统。"""
    if not settings.ENABLE_MEDIA_GENERATION:
        print("[image-gen] Media generation disabled, skipping")
        return ""
    gender_tag = "1boy" if gender == "male" else "1girl"

    prompt = (
        f"Masterpiece, best quality, 8k, {style}, {gender_tag}, "
        f"{visual_prompt_tags}, "
        f"high-end fashion photography, professional portrait, "
        f"soft studio lighting, clean background, looking at camera, "
        f"neutral expression, upper body shot"
    )

    negative = (
        "worst quality, low quality, deformed face, bad anatomy, "
        "blurry, out of focus, ugly, profile, side view, "
        "multiple people, crowd, busy background, harsh lighting"
    )

    urls = await generate_image(
        prompt=prompt,
        size="1024*1024",
        n=1,
        negative_prompt=negative,
    )

    return urls[0] if urls else ""


async def download_to_static(url: str, prefix: str = "post") -> str:
    """下载远程图片到本地 static 目录。URL 24h 过期, 必须及时下载。"""
    if not url:
        return ""
    _STATIC_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{prefix}_{uuid.uuid4().hex[:12]}.png"
    filepath = _STATIC_DIR / filename
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
        return f"/static/posts/{filename}"
    except Exception as e:
        print(f"[image_gen] Download failed: {e}")
        return url
