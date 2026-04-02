"""
记忆服务模块：提取、检索与格式化

================================================================================
功能概述
================================================================================
本模块处理 AI 伴侣记忆的完整生命周期：
1. 从对话中提取记忆片段（通过 qwen-max 模型）
2. 将记忆存储到 SQLite（关系型）和 ChromaDB（向量数据库）
3. 检索相关记忆用于上下文注入
4. 格式化记忆用于系统提示词注入

================================================================================
设计理念
================================================================================
1. 双重存储架构：
   - SQLite：关系型存储，支持结构化查询和事务
   - ChromaDB：向量存储，支持语义相似度检索

2. 亲密度门控：
   - Lv 0-5：只能访问 "fact" 类型记忆（浅层：姓名、工作、爱好）
   - Lv 6-10：可以访问 "fact" 和 "emotion" 类型记忆（深层：感受、历史）

3. 记忆保真度层级：
   - [fresh]（< 24小时）：精确回忆
   - [fading]（1-7天）：模糊回忆，可能有些细节不准确
   - [distant]（> 7天）：只记得核心感受

4. Fire-and-forget 后台任务：记忆提取不阻塞主聊天流程

================================================================================
主要组件
================================================================================
- extract_and_store_memories(): 从对话中提取并存储记忆
- get_contextual_memories(): 检索与当前对话相关的记忆
- format_memories_for_prompt(): 格式化记忆用于系统提示词注入
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from core.config import settings
from core.database import async_session
from models.memory_entry import MemoryEntry
from services import embedding_service, vector_store
from services.aliyun_ai_service import _get_client

logger = logging.getLogger(__name__)

# ── 记忆提取提示词 ──────────────────────────────────────────

_EXTRACTION_SYSTEM_PROMPT = """\
You are a memory extraction assistant. Analyze the following conversation \
between a user and an AI companion. Extract key facts and emotional states \
worth remembering for future conversations.

Output a JSON array of memory objects. Each object has:
- "type": either "fact" (concrete information like name, job, hobby, location, \
preference, schedule) or "emotion" (feelings, moods, personal struggles, \
emotional events, relationships)
- "content": a concise third-person statement about the user (e.g., \
"User's name is Alice", "User felt sad about their breakup")

Rules:
- Only extract genuinely memorable information, not trivial chat.
- Write content in third person about the user.
- Return an empty array [] if nothing worth remembering was said.
- Return ONLY the JSON array, no other text.\
"""


async def extract_and_store_memories(
    user_id: int,
    ai_id: int,
    user_message: str,
    ai_reply: str,
) -> None:
    """
    从对话回合中提取记忆片段并存储。

    作为 fire-and-forget 后台任务运行，使用独立的数据库会话。
    永远不会抛出异常 —— 所有错误都会被记录日志。

    记忆提取流程：
    1. 调用 LLM 分析对话，提取关键事实和情感状态
    2. 解析 LLM 返回的 JSON 数组
    3. 批量生成记忆内容的嵌入向量
    4. 将记忆存储到 ChromaDB（向量检索）和 SQLite（关系查询）

    记忆类型：
    - "fact"：具体信息（姓名、工作、爱好、地点、偏好、日程）
    - "emotion"：情感状态（感受、情绪、个人困扰、情感事件、关系）

    Args:
        user_id: 用户 ID
        ai_id: AI 人格 ID
        user_message: 用户消息内容
        ai_reply: AI 回复内容
    """
    try:
        client = _get_client()
        response = await client.chat.completions.create(
            model=settings.DASHSCOPE_CHAT_MODEL,  # 使用 qwen-max 进行记忆提取
            messages=[
                {"role": "system", "content": _EXTRACTION_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f'User said: "{user_message}"\n'
                        f'AI replied: "{ai_reply}"'
                    ),
                },
            ],
            temperature=0.3,  # 较低温度，确保提取结果稳定
            max_tokens=500,
        )
        raw = response.choices[0].message.content.strip()

        # 去除 Markdown 代码块标记（如果存在）
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]  # 移除第一行 ``` 标记
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        fragments = json.loads(raw)
        if not isinstance(fragments, list) or not fragments:
            return

        # 批量生成嵌入向量
        contents = [f["content"] for f in fragments if f.get("content")]
        if not contents:
            return
        embeddings = await embedding_service.get_embeddings(contents)

        # 存储每个记忆片段
        async with async_session() as db:
            for i, fragment in enumerate(fragments):
                content = fragment.get("content", "")
                mem_type = fragment.get("type", "fact")
                if mem_type not in ("fact", "emotion"):
                    mem_type = "fact"
                if not content or i >= len(embeddings):
                    continue

                vid = uuid.uuid4().hex

                # 存储到 ChromaDB（同步操作，在线程中运行）
                metadata = {
                    "user_id": str(user_id),
                    "ai_id": str(ai_id),
                    "memory_type": mem_type,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await asyncio.to_thread(
                    vector_store.add_memory, vid, embeddings[i], content, metadata
                )

                # 存储到 SQLite
                entry = MemoryEntry(
                    user_id=user_id,
                    ai_id=ai_id,
                    content=content,
                    memory_type=mem_type,
                    vector_id=vid,
                )
                db.add(entry)

            await db.commit()

        logger.info(
            "Stored %d memories for user_id=%d ai_id=%d",
            len(fragments), user_id, ai_id,
        )

    except Exception:
        logger.exception("Memory extraction failed (user_id=%d ai_id=%d)", user_id, ai_id)


# ── 记忆检索 ──────────────────────────────────────────────────

async def get_contextual_memories(
    user_id: int,
    ai_id: int,
    query_text: str,
    intimacy: float,
    top_k: int = 5,
    precomputed_embedding: list[float] | None = None,
) -> list[dict]:
    """
    检索与当前对话上下文相关的记忆。

    亲密度门控：
      - Lv 0-5：只能访问 "fact" 类型记忆（浅层：姓名、工作、爱好）
      - Lv 6-10：可以访问 "fact" 和 "emotion" 类型记忆（深层：感受、历史）

    始终按 user_id 过滤 —— 严格的多租户隔离。
    返回包含类型、内容、相关性和年龄（小时）的字典列表，用于保真度层级。

    Args:
        user_id: 用户 ID
        ai_id: AI 人格 ID
        query_text: 查询文本（用于语义相似度检索）
        intimacy: 亲密度分数 (0-10)
        top_k: 返回的记忆数量上限（默认 5）
        precomputed_embedding: 预计算的嵌入向量（可选，避免重复计算）

    Returns:
        list[dict]: 记忆字典列表，每个字典包含：
            - type: 记忆类型 ("fact" 或 "emotion")
            - content: 记忆内容
            - relevance: 相关性分数 (0-1)
            - age_hours: 记忆年龄（小时）
    """
    # 获取查询嵌入向量
    embedding = precomputed_embedding or await embedding_service.get_embedding(query_text)

    # 根据亲密度确定可访问的记忆类型
    memory_types: Optional[list[str]] = ["fact"] if intimacy < 6 else None

    # 在线程中执行向量检索（ChromaDB 是同步的）
    results = await asyncio.to_thread(
        vector_store.query_memories,
        embedding, user_id, ai_id, top_k, memory_types,
    )

    # 计算每个记忆的年龄
    now = datetime.now(timezone.utc)
    memories = []
    for r in results:
        created_str = r["metadata"].get("created_at", "")
        if created_str:
            try:
                created_dt = datetime.fromisoformat(created_str)
                age_hours = (now - created_dt).total_seconds() / 3600
            except (ValueError, TypeError):
                age_hours = 999.0  # 解析错误 → 视为远期记忆
        else:
            age_hours = 999.0  # 无时间戳（遗留数据）→ 视为远期记忆

        memories.append({
            "type": r["metadata"].get("memory_type", "fact"),
            "content": r["content"],
            "relevance": 1.0 - r["distance"],  # 将距离转换为相关性
            "age_hours": age_hours,
        })

    return memories


# ── 保真度辅助函数 ───────────────────────────────────────────

# 保真度阈值常量
_FIDELITY_FRESH_HOURS = 24       # < 24小时 → 精确回忆
_FIDELITY_FADING_HOURS = 168     # 24小时-7天 → 模糊回忆


def _age_tier(age_hours: float) -> str:
    """
    将记忆年龄分类为回忆保真度层级。

    保真度层级决定了 AI 回忆记忆时的方式：
    - "fresh"：精确回忆，可以引用细节
    - "fading"：模糊回忆，可能有些细节不准确
    - "distant"：只记得核心感受，细节已模糊

    Args:
        age_hours: 记忆年龄（小时）

    Returns:
        str: 保真度层级 ("fresh", "fading", 或 "distant")
    """
    if age_hours < _FIDELITY_FRESH_HOURS:
        return "fresh"
    if age_hours < _FIDELITY_FADING_HOURS:
        return "fading"
    return "distant"


# ── 格式化 ─────────────────────────────────────────────────

# 回忆指南：指导 AI 如何根据保真度层级回忆记忆
_RECALL_GUIDE = (
    "\nMemory Recall Rules:\n"
    "- [fresh]: You recall these clearly. Reference them precisely.\n"
    "- [fading]: You remember the pattern/emotion, but names, dates, numbers "
    "may be slightly off. Paraphrase rather than quote. "
    "Say \"I think...\" or \"wasn't it something like...\"\n"
    "- [distant]: You recall only the core feeling. Specific names, dates, "
    "times have faded. Say things like \"I vaguely remember...\" or "
    "\"didn't you once mention...\"\n"
    "This is natural — nobody remembers everything perfectly."
)


def format_memories_for_prompt(memories: list[dict]) -> str:
    """
    将检索到的记忆格式化为系统提示词注入块。

    每个记忆都标记有回忆保真度层级（基于其年龄）：
      - [fresh]   (< 24小时) — 精确回忆
      - [fading]  (1-7天) — 模糊回忆
      - [distant] (> 7天或未知年龄) — 只记得核心感受

    如果没有记忆则返回空字符串（保持新用户提示词简洁）。

    Args:
        memories: 记忆字典列表（来自 get_contextual_memories）

    Returns:
        str: 格式化的记忆块，用于注入系统提示词
    """
    if not memories:
        return ""

    lines = []
    for m in memories:
        tag = m.get("type", "fact")
        tier = _age_tier(m.get("age_hours", 999.0))
        lines.append(f"- [{tag}] [{tier}] {m['content']}")

    return (
        "## Your Memories About This User\n"
        "You remember the following about the person you're chatting with:\n"
        + "\n".join(lines) + "\n\n"
        "Use these memories naturally in conversation. Reference them when relevant, "
        "but don't list them mechanically. Never reveal that you have a 'memory system'.\n"
        + _RECALL_GUIDE
    )