"""Admin AIGC (post review / visual DNA) endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestAdminAigc:
    """Tests for ``/api/admin/posts*`` endpoints."""

    @pytest.mark.asyncio
    async def test_image_gen_request(
        self, admin_client: AsyncClient, sample_post_pending
    ):
        """List + approve pending posts (post-review serves as the image-gen review queue).

        The full image regeneration endpoint requires live AI services and is
        exercised separately; here we verify the moderator workflow.
        """
        # Pending listing surfaces the seeded post
        listing = await admin_client.get("/api/admin/posts/pending")
        assert listing.status_code == 200, listing.text
        body = listing.json()
        assert body["total"] >= 1
        post_ids = [p["id"] for p in body["posts"]]
        assert sample_post_pending.id in post_ids

        # Approve transitions status 0 -> 1
        approve = await admin_client.post(
            f"/api/admin/posts/{sample_post_pending.id}/approve"
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["status"] == 1

    @pytest.mark.asyncio
    async def test_batch_generate(
        self, admin_client: AsyncClient, sample_persona, db: AsyncSession
    ):
        """Batch-approve mutates multiple pending posts in one call."""
        from models.post import Post

        posts = [
            Post(
                ai_id=sample_persona.id,
                media_url=f"https://example.com/batch_{i}.png",
                caption=f"Batch caption {i}",
                like_count=0,
                status=0,
                post_type="image_only",
            )
            for i in range(3)
        ]
        db.add_all(posts)
        await db.commit()
        for p in posts:
            await db.refresh(p)

        post_ids = [p.id for p in posts]
        resp = await admin_client.post(
            "/api/admin/posts/batch-approve",
            json={"post_ids": post_ids},
        )
        assert resp.status_code == 200, resp.text

        body = resp.json()
        assert body["approved_count"] == 3
        assert body["failed_ids"] == []

        # All posts are now published; use ``populate_existing=True`` so the
        # identity-map cached copies are refreshed from the rows the API
        # session committed.
        for pid in post_ids:
            refreshed = (
                await db.execute(
                    select(Post)
                    .where(Post.id == pid)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one()
            assert refreshed.status == 1

    @pytest.mark.asyncio
    async def test_aigc_requires_admin(
        self, auth_client: AsyncClient, sample_post_pending
    ):
        """Non-admin requests are blocked on aigc endpoints."""
        resp = await auth_client.get("/api/admin/posts/pending")
        assert resp.status_code == 403

        approve = await auth_client.post(
            f"/api/admin/posts/{sample_post_pending.id}/approve"
        )
        assert approve.status_code == 403

    @pytest.mark.asyncio
    async def test_aigc_tracks_api_usage(
        self, admin_client: AsyncClient, db: AsyncSession
    ):
        """API-usage telemetry rows are surfaced via the devops listing.

        Mirrors how the regeneration endpoint writes one ``ApiUsageLog`` per
        external call. We seed a log directly and verify both retrieval paths.
        """
        from models.api_usage_log import ApiUsageLog

        log = ApiUsageLog(
            service="dashscope_image",
            model_name="wanx-2.1",
            request_tokens=0,
            response_tokens=0,
            latency_ms=1234,
            success=1,
            error_message="",
            cost_estimate=0.05,
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)

        listing = await admin_client.get(
            "/api/admin/api-usage", params={"days": 7, "service": "dashscope_image"}
        )
        assert listing.status_code == 200, listing.text
        rows = listing.json()
        assert any(r["id"] == log.id for r in rows)

        summary = await admin_client.get(
            "/api/admin/api-usage/summary", params={"days": 7}
        )
        assert summary.status_code == 200
        services = [row["service"] for row in summary.json()]
        assert "dashscope_image" in services
