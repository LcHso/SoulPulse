"""
Admin sandbox service - Direct DashScope API calls for prompt testing.
Does NOT touch chat_service.py. Fully isolated from production chat pipeline.
"""

import logging
from core.config import settings

logger = logging.getLogger("soulpulse.admin.sandbox")


async def sandbox_chat(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
) -> str:
    """
    Call DashScope API directly for prompt sandbox testing.
    No persistence, no memory injection, no emotion updates.
    """
    import httpx

    chat_model = model or settings.DASHSCOPE_CHAT_MODEL
    api_key = settings.DASHSCOPE_API_KEY
    if not api_key:
        return "[Error: DASHSCOPE_API_KEY not configured]"

    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": chat_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.8,
        "max_tokens": 1000,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error("Sandbox chat failed: %s", e)
        return f"[Sandbox Error: {str(e)}]"
