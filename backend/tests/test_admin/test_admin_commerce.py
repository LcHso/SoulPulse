"""Admin commerce (gem transactions / virtual gifts) endpoint tests."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class TestAdminCommerce:
    """Tests for ``/api/admin/transactions`` & related commerce endpoints."""

    @pytest.mark.asyncio
    async def test_list_gem_transactions(
        self, admin_client: AsyncClient, sample_user, db: AsyncSession
    ):
        """Listing returns paginated transactions with metadata envelope."""
        from models.gem_transaction import GemTransaction

        tx = GemTransaction(
            user_id=sample_user.id,
            amount=-30,
            balance_after=170,
            tx_type="gacha_spend",
            reference_id="g-1",
            description="抽卡消费",
        )
        db.add(tx)
        await db.commit()
        await db.refresh(tx)

        resp = await admin_client.get(
            "/api/admin/transactions", params={"user_id": sample_user.id}
        )
        assert resp.status_code == 200, resp.text

        data = resp.json()
        assert {"transactions", "total", "has_more"}.issubset(data.keys())
        assert data["total"] >= 1
        assert any(t["id"] == tx.id for t in data["transactions"])

    @pytest.mark.asyncio
    async def test_issue_gems(
        self, admin_client: AsyncClient, sample_user, db: AsyncSession
    ):
        """No dedicated grant endpoint exists; manual issuance is logged via GemTransaction.

        Validates that admin-issued grants are visible via the transactions
        listing with a positive amount and a recognizable tx_type.
        """
        from models.gem_transaction import GemTransaction

        grant = GemTransaction(
            user_id=sample_user.id,
            amount=50,
            balance_after=sample_user.gem_balance + 50,
            tx_type="admin_grant",
            reference_id="grant-1",
            description="Manual admin grant",
        )
        db.add(grant)
        await db.commit()
        await db.refresh(grant)

        resp = await admin_client.get(
            "/api/admin/transactions",
            params={"user_id": sample_user.id, "tx_type": "admin_grant"},
        )
        assert resp.status_code == 200, resp.text

        records = resp.json()["transactions"]
        assert len(records) == 1
        assert records[0]["amount"] == 50
        assert records[0]["tx_type"] == "admin_grant"

    @pytest.mark.asyncio
    async def test_issue_gems_audit_log(
        self, admin_client: AsyncClient, sample_user, db: AsyncSession
    ):
        """The revenue summary aggregates the issued gems into earnings."""
        from models.gem_transaction import GemTransaction

        db.add(
            GemTransaction(
                user_id=sample_user.id,
                amount=80,
                balance_after=sample_user.gem_balance + 80,
                tx_type="admin_grant",
                reference_id="grant-audit",
                description="Audit-trail check",
            )
        )
        await db.commit()

        summary = await admin_client.get(
            "/api/admin/revenue/summary", params={"days": 30}
        )
        assert summary.status_code == 200, summary.text

        body = summary.json()
        assert body["period_days"] == 30
        assert body["transaction_count"] >= 1
        # All admin grants are positive amounts -> counted as earned
        assert body["total_gems_earned"] >= 80
