"""Quick test of the admin delete endpoint."""
import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(base_url="http://localhost:8001") as c:
        # Login as admin (OAuth2 form)
        r = await c.post("/api/auth/login", data={"username": "admin@soulpulse.com", "password": "admin123"})
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Test delete on non-existent post -> expect 404
        r = await c.delete("/api/admin/posts/99999", headers=headers)
        print(f"Delete 99999: status={r.status_code} body={r.json()}")

        # List all posts
        r = await c.get("/api/admin/posts/all?limit=3", headers=headers)
        data = r.json()
        total = data.get("total", 0)
        ids = [p["id"] for p in data.get("posts", [])]
        print(f"All posts: total={total}, first 3 ids={ids}")

asyncio.run(test())
