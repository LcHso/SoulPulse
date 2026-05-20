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

# ── 动漫/2D 插画风格锚点 ──────────────────────────────────────────
# Genshin Impact / Love and Deepspace 同等品质基准
# 所有图片生成强制套用以下风格关键词，确保整站视觉统一
ANIME_STYLE_POSITIVE = (
    "anime illustration, clean lineart, vibrant colors, professional character design, "
    "bishounen, detailed eyes, high quality, masterpiece, best quality, "
    "anime coloring, cel shading"
)

ANIME_STYLE_NEGATIVE = (
    "photorealistic, 3D render, uncanny valley, deformed, blurry, low quality, "
    "bad anatomy, bad hands, extra fingers, fewer fingers, cropped, worst quality, "
    "jpeg artifacts, signature, watermark, username, realistic photo"
)

# CG 插画专用：戏剧光影 + 影视化构图
ANIME_CG_POSITIVE = (
    "anime CG, key visual, dramatic lighting, cinematic composition, "
    "ultra detailed, illustration, official art, bishounen"
)

# ── 强制质量保护 ──────────────────────────────────────────
# 历史负面词与新动漫风格负面词合并
ENFORCED_NEGATIVE_PROMPT = (
    f"{ANIME_STYLE_NEGATIVE}, "
    "missing fingers, extra limbs, disfigured, poorly drawn face, mutation, "
    "text, overexposed, underexposed"
)

# 风格后缀：所有 prompt 均会附加该后缀以保证 anime 风格落地
QUALITY_SUFFIX = ANIME_STYLE_POSITIVE

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


def _apply_outfit_override(prompt: str, outfit_override: dict | None) -> str:
    """将服装/场景覆写词拼接到原 prompt 的最前面，
    保证模型优先采纳当前服装与场景描述。

    outfit_override 示例: {"visual_prompt_override": "...", "scene_prompt": "..."}
    """
    if not outfit_override:
        return prompt
    parts: list[str] = []
    visual = outfit_override.get("visual_prompt_override")
    scene = outfit_override.get("scene_prompt")
    if visual:
        parts.append(visual)
    if scene:
        parts.append(scene)
    parts.append(prompt)
    return ", ".join(p for p in parts if p)


async def get_active_outfit(
    db,
    persona_id: int,
    user_id: int | None = None,
    emotion_state: dict | None = None,
) -> dict | None:
    """根据优先级选择适用于当前图片生成的服装。

    选择优先级：
    1. 当前激活的世界事件覆写 (event 型 unlock_condition)
    2. 用户手动选择的服装 (预留接口，后续特性)
    3. 情绪驱动的默认选择规则
    4. is_default 服装兑底

    返回：
        {"visual_prompt_override": "...", "scene_prompt": "..."} 或 None
    """
    from sqlalchemy import select

    from models.outfit_config import OutfitConfig

    # ── 1) 世界事件驱动的服装覆写 ──
    try:
        from datetime import datetime, timezone

        from models.world_event import WorldEvent

        now = datetime.now(timezone.utc)
        event_result = await db.execute(
            select(WorldEvent).where(WorldEvent.is_active == True)
        )
        for event in event_result.scalars().all():
            # 范围检查 (兼容 timezone-aware 与 naive datetime)
            def _cmp_dt(dt):
                # 将事件中的 dt 与 now 对齐为 timezone-naive 进行比较
                if dt is None:
                    return None
                return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

            now_naive = now.replace(tzinfo=None)
            ev_start = _cmp_dt(event.start_date)
            ev_end = _cmp_dt(event.end_date)
            start_ok = ev_start is None or ev_start <= now_naive
            end_ok = ev_end is None or ev_end >= now_naive
            if not (start_ok and end_ok):
                continue
            # 限定受影响的 persona
            affected = event.affected_persona_ids or []
            if affected and persona_id not in affected:
                continue
            # 查找该事件下可用的服装 (unlock_condition_json.type=event 且 event_id 匹配)
            ev_outfit_result = await db.execute(
                select(OutfitConfig).where(
                    OutfitConfig.persona_id == persona_id,
                    OutfitConfig.is_active == True,
                ).order_by(OutfitConfig.sort_order)
            )
            for outfit in ev_outfit_result.scalars().all():
                cond = outfit.unlock_condition_json or {}
                if cond.get("type") == "event" and cond.get("event_id") == event.id:
                    return {
                        "visual_prompt_override": outfit.visual_prompt_override,
                        "scene_prompt": outfit.scene_prompt,
                    }
    except Exception as e:  # 世界事件是可选软依赖，查询失败不阻断主流程
        print(f"[image-gen] world-event outfit lookup skipped: {e}")

    # ── 2) 用户手动选择服装的接口预留（待后续优先级增强）──
    # if user_id is not None:  TODO: 查询 user_active_outfit 表

    # ── 3) 情绪驱动的分类选择规则 ──
    if emotion_state:
        pleasure = emotion_state.get("pleasure", 0) or 0
        energy = emotion_state.get("energy", 50) or 50
        activation = emotion_state.get("activation", 0) or 0

        if pleasure < -0.3:
            target_category = "sleepwear"
        elif energy > 80 and activation > 0.5:
            target_category = "workout"
        elif energy > 60 and pleasure > 0.4:
            target_category = "formal"
        else:
            target_category = "daily"
    else:
        target_category = "daily"

    result = await db.execute(
        select(OutfitConfig).where(
            OutfitConfig.persona_id == persona_id,
            OutfitConfig.category == target_category,
            OutfitConfig.is_active == True,
        ).order_by(OutfitConfig.sort_order).limit(1)
    )
    outfit = result.scalar_one_or_none()
    if outfit:
        return {
            "visual_prompt_override": outfit.visual_prompt_override,
            "scene_prompt": outfit.scene_prompt,
        }

    # ── 4) 默认服装兑底 ──
    default_result = await db.execute(
        select(OutfitConfig).where(
            OutfitConfig.persona_id == persona_id,
            OutfitConfig.is_default == True,
            OutfitConfig.is_active == True,
        ).limit(1)
    )
    default_outfit = default_result.scalar_one_or_none()
    if default_outfit:
        return {
            "visual_prompt_override": default_outfit.visual_prompt_override,
            "scene_prompt": default_outfit.scene_prompt,
        }

    return None


async def generate_image(
    prompt: str,
    size: str | None = None,
    n: int = 1,
    persona_id: int | None = None,
    negative_prompt: str | None = None,
    outfit_override: dict | None = None,
) -> list[str]:
    """从文本提示生成图片。自动根据模型名选择 API 格式。

    Args:
        prompt: 图像生成提示词
        size: 图像尺寸（如 "720*1280"），为 None 时随机选择
        n: 生成数量
        persona_id: 角色ID（用于种子一致性）
        negative_prompt: 负面提示词
        outfit_override: 服装/场景覆写 dict，会被拼接到 prompt 最前面

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

    # 服装/场景覆写词优先于原 prompt，再叠加 anime 风格锚点
    enriched_prompt = _apply_outfit_override(prompt, outfit_override)
    full_prompt = f"{ANIME_STYLE_POSITIVE}, {enriched_prompt}, {QUALITY_SUFFIX}"
    model = settings.DASHSCOPE_IMAGE_MODEL
    # 拼接用户负面词与强制负面词，确保始终排除写实/低质内容
    neg = (
        f"{ENFORCED_NEGATIVE_PROMPT}, {negative_prompt}"
        if negative_prompt
        else ENFORCED_NEGATIVE_PROMPT
    )

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
    outfit_override: dict | None = None,
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

    # 即使带面部参考，也强制叠加 anime 风格锚点，避免被参考图带偏成写实
    enriched_prompt = _apply_outfit_override(prompt, outfit_override)
    full_prompt = f"{ANIME_STYLE_POSITIVE}, {enriched_prompt}, {QUALITY_SUFFIX}"
    model = settings.DASHSCOPE_IMAGE_MODEL
    neg = (
        f"{ENFORCED_NEGATIVE_PROMPT}, {negative_prompt}"
        if negative_prompt
        else ENFORCED_NEGATIVE_PROMPT
    )
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
    style: str = "anime illustration",
) -> str:
    """生成基础肖像图, 用于角色视觉一致性系统。

    采用 anime/2D 插画风格（非写实），对标 Genshin Impact / Love and Deepspace。
    生成的肖像同时作为后续图像生成的 face reference，必须严格保持 anime 风格。
    """
    if not settings.ENABLE_MEDIA_GENERATION:
        print("[image-gen] Media generation disabled, skipping")
        return ""
    gender_tag = "1boy" if gender == "male" else "1girl"

    # anime 角色三视图基础设定，构图以正面胸像为主，便于后续作为 face reference
    prompt = (
        f"{style}, {gender_tag}, {visual_prompt_tags}, "
        f"official character design sheet, character reference, "
        f"front view portrait, upper body, looking at viewer, "
        f"neutral expression, simple plain background, "
        f"soft anime lighting, clean lineart, cel shading, "
        f"masterpiece, best quality, ultra detailed face, detailed eyes"
    )

    # 角色设定阶段，更严格地排除写实/侧脸/多人/低质
    negative = (
        "photorealistic, realistic photo, 3D render, photograph, "
        "worst quality, low quality, deformed face, bad anatomy, "
        "blurry, out of focus, ugly, profile, side view, back view, "
        "multiple people, crowd, busy background, harsh lighting, "
        "jpeg artifacts, watermark, signature, username"
    )

    urls = await generate_image(
        prompt=prompt,
        size="1024*1024",
        n=1,
        negative_prompt=negative,
    )

    return urls[0] if urls else ""


async def generate_cg_illustration(
    prompt: str,
    persona_id: int | None = None,
    face_ref_url: str | None = None,
    size: str = "1024*1536",
    negative_prompt: str | None = None,
) -> str:
    """生成高质量 CG 插画（关键剧情画面）。

    与日常立绘的差异：
    - 默认更高分辨率（1024x1536，纵向构图，适合 CG 鉴赏）
    - 叠加 ANIME_CG_POSITIVE 戏剧光影/影视构图锚点
    - 若提供 face_ref_url，会通过面部参考保持角色一致性

    Args:
        prompt: 场景描述（不含风格关键词，函数内自动补全）
        persona_id: 角色 ID，用于种子一致性
        face_ref_url: 角色 base portrait URL，可选
        size: 输出尺寸，默认 1024*1536（CG 鉴赏图常用纵版）
        negative_prompt: 用户额外的负面词，可选

    Returns:
        str: 远程图片 URL（24h 过期，需配合 download_to_static 持久化）
    """
    if not settings.ENABLE_MEDIA_GENERATION:
        print("[image-gen] Media generation disabled, skipping")
        return ""

    # CG 专用 prompt：anime 风格 + CG 构图 + 用户场景描述
    cg_prompt = f"{ANIME_CG_POSITIVE}, {prompt}"

    if face_ref_url:
        urls = await generate_image_with_face_ref(
            prompt=cg_prompt,
            face_ref_url=face_ref_url,
            size=size,
            n=1,
            persona_id=persona_id,
            negative_prompt=negative_prompt,
        )
    else:
        urls = await generate_image(
            prompt=cg_prompt,
            size=size,
            n=1,
            persona_id=persona_id,
            negative_prompt=negative_prompt,
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


# ── 视觉一致性验证钩子 (Asset Pipeline - Plan Task 5) ──────────────────────────────────────────


async def validate_consistency(generated_image_url: str, reference_image_url: str) -> float:
    """
    Validate visual consistency between generated image and reference.
    Returns similarity score 0.0 to 1.0.

    Uses perceptual comparison (placeholder implementation —
    in production would use face embedding comparison via
    a dedicated model like ArcFace or InsightFace).

    Args:
        generated_image_url: URL of the newly generated image
        reference_image_url: URL of the reference/canonical image

    Returns:
        float: Similarity score between 0.0 and 1.0
              (1.0 = identical, 0.0 = completely different)
    """
    # Placeholder: return 1.0 for now
    # TODO: Integrate face embedding comparison when available
    # Implementation plan:
    # 1. Download both images
    # 2. Extract face embeddings using ArcFace/InsightFace
    # 3. Compute cosine similarity between embeddings
    # 4. Return normalized score
    return 1.0
