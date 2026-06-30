"""
Generate character portraits using NovelAI API.

Usage:
    python3 -m scripts.generate_nai_portraits [--character NAME] [--force] [--all] [--dry-run]

Generates per character:
    - 1x base portrait (1024x1024) -> static/avatars/{slug}_portrait.png
    - 1x avatar       (512x512)    -> static/avatars/{slug}_avatar.png
    - 3x expression variants (832x1216) -> static/avatars/{slug}_expr_{emotion}.png
        emotions: smile, serious, blush

The script:
  - Reads NAI_PROMPTS from scripts.seed_personas (positive / negative / portrait tags)
  - Drives backend/services/nai_image_service.py (singleton `nai_service`)
  - Uses a deterministic per-character seed (md5 of name) for reproducibility
  - Updates ai_personas.base_face_url and ai_personas.avatar_url after success
  - Skips characters that already have portraits unless --force
  - Exits gracefully if NAI_API_KEY is missing
  - Retries each API call once before skipping
  - Sleeps 2 seconds between API calls to respect rate limits

Run from the backend directory:
    cd backend && python3 -m scripts.generate_nai_portraits
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import sys
from pathlib import Path
from typing import Optional

# Make the script runnable both as a module (-m scripts.generate_nai_portraits)
# and directly. Insert the backend dir on sys.path.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select, text  # noqa: E402

from core.config import settings  # noqa: E402
from core.database import async_session, init_db  # noqa: E402
from models.ai_persona import AIPersona  # noqa: E402
from scripts.seed_personas import NAI_PROMPTS  # noqa: E402
from services.nai_image_service import nai_service  # noqa: E402


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

# Character name -> filesystem slug used for avatar / portrait file names.
NAME_TO_SLUG: dict[str, str] = {
    "林星野": "linxingye",
    "陆骁": "luxiao",
    "季夜尘": "jiyechen",
    "顾言深": "guyanshen",
    "陆晨曦": "luchenxi",
    "沈默白": "shenmobai",
    "傅霁川": "fujichuan",
    "赫连烨": "helianye",
    "江屿白": "jiangyubai",
    "裴洛": "peiluo",
    "温时序": "wenshixu",
}

# Expression variants: emotion key -> tags appended to the positive prompt.
EXPRESSION_VARIANTS: dict[str, str] = {
    "smile": "smile, happy, cheerful expression",
    "serious": "serious expression, determined, sharp gaze",
    "blush": "blush, embarrassed, looking away, shy",
}

AVATAR_DIR = _BACKEND_DIR / "static" / "avatars"
EXPRESSION_SIZE = (832, 1216)
PORTRAIT_SIZE = 1024
AVATAR_SIZE = 512
RATE_LIMIT_DELAY_SEC = 2.0


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _persona_seed(name: str) -> int:
    """Stable seed derived from the character name for reproducibility."""
    digest = hashlib.md5(f"persona_{name}".encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) % 2147483647


def _avatar_path(slug: str, kind: str) -> Path:
    """Build absolute file path inside backend/static/avatars/."""
    return AVATAR_DIR / f"{slug}_{kind}.png"


def _to_static_url(filepath: Path) -> str:
    """Return the URL path served by FastAPI's static mount."""
    parts = filepath.as_posix().split("/static/")
    if len(parts) == 2:
        return "/static/" + parts[1]
    return filepath.as_posix()


async def _ensure_columns(db) -> None:
    """Ensure base_face_url / visual_prompt_tags columns exist on ai_personas."""
    result = await db.execute(text("PRAGMA table_info(ai_personas)"))
    existing = {row[1] for row in result.fetchall()}

    migrations = {
        "base_face_url": "ALTER TABLE ai_personas ADD COLUMN base_face_url VARCHAR(500)",
        "visual_prompt_tags": "ALTER TABLE ai_personas ADD COLUMN visual_prompt_tags TEXT",
        "visual_description": "ALTER TABLE ai_personas ADD COLUMN visual_description TEXT",
    }
    for col, sql in migrations.items():
        if col not in existing:
            print(f"  + adding missing column: {col}")
            await db.execute(text(sql))
            await db.commit()


async def _call_with_retry(coro_factory, label: str) -> Optional[bytes]:
    """Invoke an async image-generation call with one retry on failure."""
    for attempt in (1, 2):
        try:
            data = await coro_factory()
            if data:
                return data
            print(f"  [{label}] attempt {attempt} returned no data")
        except Exception as exc:  # pragma: no cover - network errors
            print(f"  [{label}] attempt {attempt} raised: {exc}")
        if attempt == 1:
            await asyncio.sleep(RATE_LIMIT_DELAY_SEC)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Per-character generation
# ──────────────────────────────────────────────────────────────────────────────

async def _generate_for_character(
    name: str,
    prompts: dict,
    force: bool,
    dry_run: bool,
) -> Optional[dict[str, str]]:
    """
    Generate portrait + avatar + expression variants for one character.

    Returns a dict with keys {portrait, avatar, expr_smile, expr_serious, expr_blush}
    pointing to the served URLs, or None if the character was skipped/failed.
    """
    slug = NAME_TO_SLUG.get(name)
    if not slug:
        print(f"[{name}] no slug mapping, skipping")
        return None

    portrait_path = _avatar_path(slug, "portrait")
    avatar_path = _avatar_path(slug, "avatar")
    expr_paths = {
        emotion: _avatar_path(slug, f"expr_{emotion}")
        for emotion in EXPRESSION_VARIANTS
    }

    # Skip-existing logic: only require the two main files for the "exists" check.
    if not force and portrait_path.exists() and avatar_path.exists():
        print(f"[{name}] portraits already exist, use --force to regenerate")
        return None

    seed = _persona_seed(name)
    positive = prompts["positive"]
    portrait_prompt = prompts["portrait"]
    negative = prompts.get("negative") or None

    print(f"[{name}] slug={slug} seed={seed}")
    if dry_run:
        print(f"  (dry-run) portrait -> {portrait_path}")
        print(f"  (dry-run) avatar   -> {avatar_path}")
        for emotion, p in expr_paths.items():
            print(f"  (dry-run) expr[{emotion}] -> {p}")
        return None

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    saved: dict[str, str] = {}

    # 1. Base portrait (1024x1024) - uses the curated `portrait` prompt
    print(f"  Generating portrait for {name}...", end=" ", flush=True)
    img = await _call_with_retry(
        lambda: nai_service.generate_image(
            prompt=portrait_prompt,
            negative_prompt=negative,
            width=PORTRAIT_SIZE,
            height=PORTRAIT_SIZE,
            seed=seed,
            scale=5.5,
        ),
        label="portrait",
    )
    if not img:
        print("failed: NAI returned no image after retry")
        return None
    await nai_service.save_image(img, str(portrait_path))
    saved["portrait"] = _to_static_url(portrait_path)
    print("done")
    await asyncio.sleep(RATE_LIMIT_DELAY_SEC)

    # 2. Avatar (512x512) - close-up face, reuse positive tags via service helper
    print(f"  Generating avatar for {name}...", end=" ", flush=True)
    img = await _call_with_retry(
        lambda: nai_service.generate_avatar(
            character_tags=positive,
            seed=seed,
        ),
        label="avatar",
    )
    if not img:
        print("failed: NAI returned no image after retry")
        return saved or None
    await nai_service.save_image(img, str(avatar_path))
    saved["avatar"] = _to_static_url(avatar_path)
    print("done")
    await asyncio.sleep(RATE_LIMIT_DELAY_SEC)

    # 3. Expression variants (832x1216) - positive prompt + emotion tags
    for emotion, extra_tags in EXPRESSION_VARIANTS.items():
        out_path = expr_paths[emotion]
        # Vary seed per emotion so faces aren't identical poses.
        emotion_seed = (seed + sum(ord(c) for c in emotion)) % 2147483647
        expr_prompt = (
            f"1person, upper body, looking at viewer, simple background, "
            f"{positive}, {extra_tags}"
        )
        print(f"  Generating expr[{emotion}] for {name}...", end=" ", flush=True)
        img = await _call_with_retry(
            lambda p=expr_prompt, s=emotion_seed: nai_service.generate_image(
                prompt=p,
                negative_prompt=negative,
                width=EXPRESSION_SIZE[0],
                height=EXPRESSION_SIZE[1],
                seed=s,
                scale=5.5,
            ),
            label=f"expr-{emotion}",
        )
        if not img:
            print("failed: skipped")
            continue
        await nai_service.save_image(img, str(out_path))
        saved[f"expr_{emotion}"] = _to_static_url(out_path)
        print("done")
        await asyncio.sleep(RATE_LIMIT_DELAY_SEC)

    return saved


# ──────────────────────────────────────────────────────────────────────────────
# DB update
# ──────────────────────────────────────────────────────────────────────────────

async def _update_persona_record(
    db, name: str, portrait_url: str, avatar_url: str, positive_tags: str
) -> None:
    """Write generated URLs back to ai_personas."""
    result = await db.execute(select(AIPersona).where(AIPersona.name == name))
    persona = result.scalars().first()
    if not persona:
        print(f"  [db] persona '{name}' not found, skipping DB update")
        return
    persona.base_face_url = portrait_url
    persona.avatar_url = avatar_url
    if not getattr(persona, "visual_prompt_tags", None):
        persona.visual_prompt_tags = positive_tags
    await db.commit()
    print(f"  [db] updated persona id={persona.id}: base_face_url+avatar_url")


# ──────────────────────────────────────────────────────────────────────────────
# Main orchestration
# ──────────────────────────────────────────────────────────────────────────────

async def run(
    character: Optional[str],
    force: bool,
    dry_run: bool,
) -> int:
    if not settings.NAI_API_KEY and not dry_run:
        print(
            "[nai-portraits] WARNING: NAI_API_KEY is not set in the environment.\n"
            "                Set it in backend/.env before running this script.\n"
            "                Exiting gracefully without making any API calls."
        )
        return 1

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    if character:
        if character not in NAI_PROMPTS:
            print(f"[nai-portraits] Unknown character '{character}'.")
            print(f"  Known characters: {', '.join(NAI_PROMPTS.keys())}")
            return 2
        targets = [character]
    else:
        targets = list(NAI_PROMPTS.keys())

    print(f"[nai-portraits] backend     = {settings.IMAGE_BACKEND}")
    print(f"[nai-portraits] model       = {settings.NAI_MODEL}")
    print(f"[nai-portraits] output dir  = {AVATAR_DIR}")
    print(f"[nai-portraits] characters  = {len(targets)}")
    print(f"[nai-portraits] force       = {force}")
    print(f"[nai-portraits] dry-run     = {dry_run}")
    print("=" * 64)

    if not dry_run:
        await init_db()

    successes = 0
    failures: list[str] = []

    async def _run_all(db) -> None:
        nonlocal successes
        for name in targets:
            prompts = NAI_PROMPTS[name]
            try:
                saved = await _generate_for_character(name, prompts, force, dry_run)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[{name}] unexpected error: {exc}")
                failures.append(name)
                continue

            if not saved:
                if not dry_run:
                    failures.append(name)
                continue

            successes += 1
            if dry_run:
                continue

            portrait_url = saved.get("portrait")
            avatar_url = saved.get("avatar") or portrait_url
            if portrait_url and avatar_url:
                await _update_persona_record(
                    db,
                    name=name,
                    portrait_url=portrait_url,
                    avatar_url=avatar_url,
                    positive_tags=prompts["positive"],
                )

    if dry_run:
        await _run_all(db=None)
    else:
        async with async_session() as db:
            await _ensure_columns(db)
            await _run_all(db)

    print("=" * 64)
    print(f"[nai-portraits] success: {successes}/{len(targets)}")
    if failures:
        print(f"[nai-portraits] failed : {', '.join(failures)}")
    print("[nai-portraits] done")
    return 0 if not failures else 3


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate NAI portraits/avatars/expressions for SoulPulse personas."
    )
    parser.add_argument(
        "--character",
        type=str,
        default=None,
        help="Generate for a single character (Chinese name). Omit for all.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing portraits/avatars on disk.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Generate for every character (default behavior when --character is absent).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be generated, without calling the NAI API or touching DB.",
    )
    return parser.parse_args()


async def _main_async() -> int:
    args = _parse_args()
    target = args.character
    if not target and not args.all:
        # Default to --all when neither flag is given.
        target = None
    return await run(character=target, force=args.force, dry_run=args.dry_run)


def main() -> None:
    exit_code = asyncio.run(_main_async())
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
