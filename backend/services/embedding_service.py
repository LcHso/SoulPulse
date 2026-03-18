from openai import AsyncOpenAI

from core.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.DASHSCOPE_API_KEY,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    return _client


async def get_embedding(text: str) -> list[float]:
    """Generate embedding for a single text via DashScope text-embedding-v3."""
    client = _get_client()
    response = await client.embeddings.create(
        model=settings.DASHSCOPE_EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0].embedding


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for multiple texts in a single API call."""
    if not texts:
        return []
    client = _get_client()
    response = await client.embeddings.create(
        model=settings.DASHSCOPE_EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]
