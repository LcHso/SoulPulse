"""
Character Card Endpoint Tests

Tests for SillyTavern V2 character card import/export endpoints in
``api/endpoints/character_cards.py``:

- GET  /character-cards/{persona_id}/export      → JSON card export
- GET  /character-cards/{persona_id}/export-png  → PNG card export
- POST /character-cards/import                    → Import card (PNG / JSON)
- POST /character-cards/convert-markdown          → Markdown → Tavern card
"""

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# Minimal valid 1x1 RGBA PNG (used for PNG export tests).
MIN_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _build_valid_card(name: str = "Imported Char") -> dict:
    """Construct a minimal but complete SillyTavern V2 card dict."""
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": name,
            "description": "A friendly imported test character.",
            "personality": "warm, attentive, creative",
            "scenario": "Sitting in a quiet cafe at dusk.",
            "first_mes": "Hi there, mind if I sit with you?",
            "mes_example": "<START>\n{{user}}: Hello\n{{char}}: Hi!",
            "creator_notes": "test card",
            "system_prompt": (
                "You are Imported Char, a kind soul who listens carefully "
                "and replies with gentle warmth."
            ),
            "post_history_instructions": "",
            "tags": ["otome", "test"],
            "creator": "pytest",
            "character_version": "1.0",
            "extensions": {
                "visual_dna": "1girl, brown_hair, soft_smile",
                "secret_layers": "Has stage fright when performing solo.",
            },
        },
    }


# ────────────────────────────────────────────────────────────────────
# Export – JSON
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_card_json(client: AsyncClient, sample_persona):
    """GET /character-cards/{id}/export returns SillyTavern V2 JSON."""
    resp = await client.get(f"/character-cards/{sample_persona.id}/export")
    assert resp.status_code == 200, resp.text

    card = resp.json()
    assert card["spec"] == "chara_card_v2"
    assert card["spec_version"] == "2.0"
    assert "data" in card
    assert card["data"]["name"] == sample_persona.name


@pytest.mark.asyncio
async def test_export_card_not_found(client: AsyncClient):
    """Exporting an unknown persona returns 404."""
    resp = await client.get("/character-cards/999999/export")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_export_includes_all_fields(client: AsyncClient, sample_persona):
    """Exported card contains every required Tavern V2 ``data`` field."""
    resp = await client.get(f"/character-cards/{sample_persona.id}/export")
    assert resp.status_code == 200

    card = resp.json()
    assert set(["spec", "spec_version", "data"]).issubset(card.keys())

    required_data_fields = {
        "name",
        "description",
        "personality",
        "scenario",
        "first_mes",
        "mes_example",
        "creator_notes",
        "system_prompt",
        "post_history_instructions",
        "tags",
        "creator",
        "character_version",
        "extensions",
    }
    assert required_data_fields.issubset(card["data"].keys())


# ────────────────────────────────────────────────────────────────────
# Export – PNG
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_card_png(
    client: AsyncClient,
    db: AsyncSession,
    sample_persona,
    tmp_path,
):
    """GET /character-cards/{id}/export-png returns valid PNG bytes."""
    # Persona avatar_url must point to a real file the endpoint can read.
    avatar_file = tmp_path / "avatar.png"
    avatar_file.write_bytes(MIN_PNG_BYTES)

    # Use an ASCII name so the Content-Disposition filename header is
    # latin-1 encodable (Starlette does not RFC 5987-encode header values).
    sample_persona.name = "AsciiPersona"
    sample_persona.avatar_url = str(avatar_file)
    db.add(sample_persona)
    await db.commit()

    resp = await client.get(f"/character-cards/{sample_persona.id}/export-png")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/png"
    # Must still be a valid PNG (signature preserved, length grew due to
    # embedded tEXt metadata chunk).
    assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(resp.content) > len(MIN_PNG_BYTES)


# ────────────────────────────────────────────────────────────────────
# Import
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_card_json(client: AsyncClient):
    """POST /character-cards/import parses a Tavern V2 JSON payload."""
    card = _build_valid_card(name="Imported Char")
    files = {
        "file": (
            "imported.json",
            json.dumps(card).encode("utf-8"),
            "application/json",
        )
    }
    resp = await client.post("/character-cards/import", files=files)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["status"] == "parsed"
    assert body["card"]["spec"] == "chara_card_v2"
    assert body["persona_data"]["name"] == "Imported Char"
    # Description from card.data.description should be mapped onto bio.
    assert body["persona_data"]["bio"] == card["data"]["description"]


@pytest.mark.asyncio
async def test_import_card_invalid_format(client: AsyncClient):
    """Uploading a file the parser cannot decode returns a 4xx error."""
    files = {
        "file": (
            "broken.json",
            b"this is not valid json or a png",
            "application/json",
        )
    }
    resp = await client.post("/character-cards/import", files=files)
    # Endpoint raises 400 for unparseable JSON; FastAPI itself would raise
    # 422 if the file param were missing entirely.  Accept both so the test
    # is robust against minor endpoint refactors.
    assert resp.status_code in (400, 422), resp.text


@pytest.mark.asyncio
async def test_import_preserves_personality(client: AsyncClient):
    """Imported persona_data.personality_prompt mirrors card system_prompt."""
    card = _build_valid_card(name="Persona Keeper")
    expected_prompt = card["data"]["system_prompt"]

    files = {
        "file": (
            "preserve.json",
            json.dumps(card).encode("utf-8"),
            "application/json",
        )
    }
    resp = await client.post("/character-cards/import", files=files)
    assert resp.status_code == 200, resp.text

    persona_data = resp.json()["persona_data"]
    assert persona_data["personality_prompt"] == expected_prompt
    # Family background is mapped from scenario.
    assert persona_data["family_background"] == card["data"]["scenario"]
    # tavern_card_json should round-trip the original payload.
    round_tripped = json.loads(persona_data["tavern_card_json"])
    assert round_tripped["data"]["name"] == "Persona Keeper"


# ────────────────────────────────────────────────────────────────────
# Convert markdown
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_convert_markdown_to_tavern(client: AsyncClient):
    """POST /character-cards/convert-markdown returns a V2 card from MD."""
    md = (
        "# 测试角色\n\n"
        "## 基础信息\n"
        "- 类型：乙女向\n"
        "- 职业：作家\n\n"
        "## 外在人格\n"
        "温柔体贴，喜欢倾听别人的故事。\n\n"
        "## 内在人格\n"
        "敏感细腻，渴望被理解。\n\n"
        "## 背景故事\n"
        "出生在一个普通的小镇家庭，从小热爱阅读。\n\n"
        "## System Prompt\n"
        "```\n"
        "你是测试角色，一位温柔的作家。\n"
        "```\n"
        "## 示例对话\n"
        "**亲密度 0-10（陌生人）：**\n"
        "> 你好，初次见面。\n"
    )
    files = {
        "file": (
            "test_character.md",
            md.encode("utf-8"),
            "text/markdown",
        )
    }
    resp = await client.post("/character-cards/convert-markdown", files=files)
    assert resp.status_code == 200, resp.text

    card = resp.json()
    assert card["spec"] == "chara_card_v2"
    assert card["spec_version"] == "2.0"
    assert card["data"]["name"] == "测试角色"
    # System prompt section should populate the system_prompt field.
    assert "测试角色" in card["data"]["system_prompt"]
    # otome tag should have been auto-detected from 基础信息.
    assert "otome" in card["data"]["tags"]
