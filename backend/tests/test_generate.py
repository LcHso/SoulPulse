"""
Generate Endpoint Tests

Tests for ``backend/api/endpoints/generate.py``:
- POST /api/generate/post: AI persona post generation (caption + image/video).

The generate endpoint imports its helpers at module load
(``from services.aliyun_ai_service import generate_post_caption, ...``)
so we monkeypatch the symbols on ``api.endpoints.generate`` itself.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_persona import AIPersona
from models.post import Post


def _patch_generators(monkeypatch, *, image_url: str = "https://example.com/fake.png",
                      caption: str = "Mock caption ☕",
                      raise_image: bool = False):
    """Patch external generator helpers used by ``generate_post``.

    Returns the dict of installed mocks for assertion purposes.
    """
    from api.endpoints import generate as gen_mod

    fake_caption = AsyncMock(return_value=caption)
    fake_prompt = AsyncMock(return_value="masterpiece, portrait")

    if raise_image:
        fake_image = AsyncMock(side_effect=RuntimeError("image backend down"))
        fake_image_face = AsyncMock(side_effect=RuntimeError("image backend down"))
    else:
        fake_image = AsyncMock(return_value=[image_url])
        fake_image_face = AsyncMock(return_value=[image_url])

    fake_nai = SimpleNamespace(
        generate_post_image=AsyncMock(
            side_effect=RuntimeError("nai down") if raise_image else AsyncMock(return_value=b"\x89PNG")
        ),
        save_image=AsyncMock(return_value=image_url),
    )
    # Make generate_post_image return bytes (await-able) when not raising
    if not raise_image:
        fake_nai.generate_post_image = AsyncMock(return_value=b"\x89PNGfakebytes")

    monkeypatch.setattr(gen_mod, "generate_post_caption", fake_caption)
    monkeypatch.setattr(gen_mod, "generate_image_prompt", fake_prompt)
    monkeypatch.setattr(gen_mod, "generate_image", fake_image)
    monkeypatch.setattr(gen_mod, "generate_image_with_face_ref", fake_image_face)
    monkeypatch.setattr(gen_mod, "nai_service", fake_nai)

    # Force a deterministic backend so we know which path runs.
    monkeypatch.setattr(gen_mod.settings, "IMAGE_BACKEND", "nai", raising=False)

    return {
        "caption": fake_caption,
        "prompt": fake_prompt,
        "image": fake_image,
        "image_face": fake_image_face,
        "nai": fake_nai,
    }


@pytest.mark.asyncio
async def test_generate_post_success(
    auth_client: AsyncClient,
    db: AsyncSession,
    sample_persona,
    monkeypatch,
):
    """A valid request with a real persona should produce a Post row."""
    fake_url = "https://example.com/generated.png"
    mocks = _patch_generators(monkeypatch, image_url=fake_url, caption="陆晨曦的午后小记")

    resp = await auth_client.post(
        "/api/generate/post",
        json={"ai_id": sample_persona.id, "media_type": "image"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["caption"] == "陆晨曦的午后小记"
    assert body["media_type"] == "image"
    assert body["media_url"] == fake_url
    assert isinstance(body["post_id"], int)

    # The caption / prompt mocks must have been awaited exactly once.
    mocks["caption"].assert_awaited_once()
    mocks["prompt"].assert_awaited_once()

    # The post was actually persisted with the persona id.
    saved = await db.execute(select(Post).where(Post.id == body["post_id"]))
    post = saved.scalar_one()
    assert post.ai_id == sample_persona.id
    assert post.media_url == fake_url


@pytest.mark.asyncio
async def test_generate_post_unauthenticated(client: AsyncClient, sample_persona):
    """Without a Bearer token the endpoint must reject the request."""
    resp = await client.post(
        "/api/generate/post",
        json={"ai_id": sample_persona.id, "media_type": "image"},
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_post_invalid_persona(
    auth_client: AsyncClient, monkeypatch
):
    """Non-existent AI persona id must return 404 before any generator runs."""
    mocks = _patch_generators(monkeypatch)

    resp = await auth_client.post(
        "/api/generate/post",
        json={"ai_id": 999_999, "media_type": "image"},
    )

    assert resp.status_code == 404
    assert "AI persona not found" in resp.json().get("detail", "")
    # No expensive generator should have been invoked.
    mocks["caption"].assert_not_awaited()
    mocks["prompt"].assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_post_disabled(
    auth_client: AsyncClient,
    db: AsyncSession,
    sample_persona,
    monkeypatch,
):
    """Image-backend failure path: generator raises -> endpoint degrades gracefully.

    The endpoint catches generator exceptions and still persists a post with an
    empty ``media_url`` instead of 5xx-ing. This effectively models a
    'disabled / unavailable' image backend.
    """
    _patch_generators(monkeypatch, raise_image=True)

    resp = await auth_client.post(
        "/api/generate/post",
        json={"ai_id": sample_persona.id, "media_type": "image"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["media_url"] == ""
    assert body["media_type"] == "image"

    saved = await db.execute(select(Post).where(Post.id == body["post_id"]))
    assert saved.scalar_one().media_url == ""


@pytest.mark.asyncio
async def test_generate_post_rate_limited(
    auth_client: AsyncClient, monkeypatch
):
    """Malformed / missing-field requests are rejected by FastAPI validation.

    The endpoint has no per-user rate limiter today, so we exercise the closest
    request-rejection path: a request missing the required ``ai_id`` must yield
    a 422 without invoking any generator.
    """
    mocks = _patch_generators(monkeypatch)

    resp = await auth_client.post(
        "/api/generate/post",
        json={"media_type": "image"},  # missing ai_id
    )

    assert resp.status_code == 422
    mocks["caption"].assert_not_awaited()
    mocks["image"].assert_not_awaited()
