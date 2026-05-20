"""
Visual Regression Testing Script - 视觉回归测试

Generates test images for each persona and compares against reference set.
Uses perceptual hashing to detect visual drift.

Usage:
    python -m scripts.visual_regression_test [--persona_id N] [--threshold 0.8]
    python -m scripts.visual_regression_test --generate-refs

Reference images are stored in backend/static/visual_refs/{persona_id}/
Test results are output to stdout and optionally written to asset_registry.
"""

import asyncio
import hashlib
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from core.database import async_session


# Reference images directory
_REFS_DIR = Path(__file__).parent.parent / "static" / "visual_refs"
_REFS_DIR.mkdir(parents=True, exist_ok=True)


def _compute_perceptual_hash(image_bytes: bytes) -> str:
    """
    Compute a basic perceptual hash for an image.

    In production, this would use imagehash (pHash/dHash) for robust
    perceptual comparison. For now, uses a simplified content hash
    that serves as a placeholder.

    Args:
        image_bytes: Raw image data

    Returns:
        Hex string hash of image content
    """
    # Basic implementation: MD5 of image bytes
    # TODO: Replace with imagehash.phash() when PIL/imagehash available
    return hashlib.md5(image_bytes).hexdigest()


def _compare_hashes(hash_a: str, hash_b: str) -> float:
    """
    Compare two perceptual hashes and return similarity score.

    With proper perceptual hashing (pHash), this would compute
    Hamming distance. With MD5 fallback, exact match = 1.0, else
    character-level similarity.

    Returns:
        float: Similarity score 0.0 to 1.0
    """
    if hash_a == hash_b:
        return 1.0

    # Character-level similarity as rough approximation
    matching = sum(a == b for a, b in zip(hash_a, hash_b))
    return matching / max(len(hash_a), len(hash_b))


async def _get_personas(persona_id: int = None) -> list:
    """Fetch personas from database."""
    from models.ai_persona import AIPersona

    async with async_session() as db:
        query = select(AIPersona)
        if persona_id:
            query = query.where(AIPersona.id == persona_id)
        result = await db.execute(query)
        return list(result.scalars().all())


async def _generate_test_image(persona) -> bytes | None:
    """
    Generate a test image for a persona using standard prompt.

    Returns raw image bytes or None if generation is disabled/failed.
    """
    import httpx
    from services.image_gen_service import generate_image

    # Standard test prompt for consistency checking
    test_prompt = (
        f"character portrait, {persona.name}, "
        f"front view, upper body, looking at viewer, neutral expression, "
        f"simple background"
    )

    try:
        urls = await generate_image(
            prompt=test_prompt,
            size="1024*1024",
            n=1,
            persona_id=persona.id,
        )
        if not urls:
            print(f"  [SKIP] No image generated for persona {persona.id} ({persona.name})")
            return None

        # Download image bytes
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(urls[0])
            resp.raise_for_status()
            return resp.content

    except Exception as e:
        print(f"  [ERROR] Failed to generate test image for {persona.name}: {e}")
        return None


async def _load_reference(persona_id: int) -> bytes | None:
    """Load reference image bytes for a persona."""
    ref_path = _REFS_DIR / str(persona_id) / "reference.png"
    if ref_path.exists():
        return ref_path.read_bytes()
    return None


async def _save_reference(persona_id: int, image_bytes: bytes):
    """Save reference image for a persona."""
    ref_dir = _REFS_DIR / str(persona_id)
    ref_dir.mkdir(parents=True, exist_ok=True)
    ref_path = ref_dir / "reference.png"
    ref_path.write_bytes(image_bytes)
    print(f"  [SAVED] Reference image for persona {persona_id}")


async def run_regression_test(persona_id: int = None, threshold: float = 0.8):
    """
    Run visual regression test:
    1. For each persona (or specified one):
       a. Generate a test image using standard prompt
       b. Load reference image from stored set
       c. Compare using perceptual hash
       d. Record score
    2. Generate summary report
    3. Flag any persona below threshold
    """
    print("=" * 60)
    print("  SoulPulse Visual Regression Test")
    print("=" * 60)

    personas = await _get_personas(persona_id)
    if not personas:
        print("[ERROR] No personas found")
        return

    results = []

    for persona in personas:
        print(f"\n── Testing: {persona.name} (ID: {persona.id}) ──")

        # Load reference
        ref_bytes = await _load_reference(persona.id)
        if ref_bytes is None:
            print(f"  [SKIP] No reference image found. Run with --generate-refs first.")
            results.append({
                "persona_id": persona.id,
                "name": persona.name,
                "score": None,
                "status": "no_reference",
            })
            continue

        # Generate test image
        test_bytes = await _generate_test_image(persona)
        if test_bytes is None:
            results.append({
                "persona_id": persona.id,
                "name": persona.name,
                "score": None,
                "status": "generation_failed",
            })
            continue

        # Compare
        ref_hash = _compute_perceptual_hash(ref_bytes)
        test_hash = _compute_perceptual_hash(test_bytes)
        score = _compare_hashes(ref_hash, test_hash)

        status = "pass" if score >= threshold else "FAIL"
        results.append({
            "persona_id": persona.id,
            "name": persona.name,
            "score": score,
            "status": status,
        })
        print(f"  Score: {score:.3f} [{status}]")

    # Summary report
    print("\n" + "=" * 60)
    print("  SUMMARY REPORT")
    print("=" * 60)

    tested = [r for r in results if r["score"] is not None]
    passed = [r for r in tested if r["status"] == "pass"]
    failed = [r for r in tested if r["status"] == "FAIL"]
    skipped = [r for r in results if r["score"] is None]

    print(f"  Total personas:  {len(results)}")
    print(f"  Tested:          {len(tested)}")
    print(f"  Passed:          {len(passed)}")
    print(f"  Failed:          {len(failed)}")
    print(f"  Skipped:         {len(skipped)}")
    print(f"  Threshold:       {threshold}")

    if tested:
        avg_score = sum(r["score"] for r in tested) / len(tested)
        print(f"  Average score:   {avg_score:.3f}")

    if failed:
        print("\n  ⚠ FAILED PERSONAS:")
        for r in failed:
            print(f"    - {r['name']} (ID: {r['persona_id']}) score={r['score']:.3f}")

    print("\n" + "=" * 60)


async def generate_reference_set(persona_id: int = None):
    """Generate and store reference images for all personas (run once after style change)."""
    print("=" * 60)
    print("  Generating Reference Image Set")
    print("=" * 60)

    personas = await _get_personas(persona_id)
    if not personas:
        print("[ERROR] No personas found")
        return

    for persona in personas:
        print(f"\n── Generating reference: {persona.name} (ID: {persona.id}) ──")

        image_bytes = await _generate_test_image(persona)
        if image_bytes:
            await _save_reference(persona.id, image_bytes)
        else:
            print(f"  [SKIP] Could not generate reference for {persona.name}")

    print("\n[DONE] Reference set generation complete.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="SoulPulse Visual Regression Testing"
    )
    parser.add_argument(
        "--persona_id", type=int, default=None,
        help="Test specific persona ID (default: all)"
    )
    parser.add_argument(
        "--threshold", type=float, default=0.8,
        help="Similarity threshold for pass/fail (default: 0.8)"
    )
    parser.add_argument(
        "--generate-refs", action="store_true",
        help="Generate reference images instead of testing"
    )
    args = parser.parse_args()

    if args.generate_refs:
        asyncio.run(generate_reference_set(args.persona_id))
    else:
        asyncio.run(run_regression_test(args.persona_id, args.threshold))
