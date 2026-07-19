import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_list_repositories_empty():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/config/repositories")
        assert resp.status_code == 200
        assert resp.json() == []


@pytest.mark.asyncio
async def test_register_repository():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/config/repositories",
            json={"repo_url": "http://gitlab/test/repo.git"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "registered"


@pytest.mark.asyncio
async def test_register_duplicate():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/config/repositories",
            json={"repo_url": "http://gitlab/dup.git"},
        )
        resp = await client.post(
            "/api/v1/config/repositories",
            json={"repo_url": "http://gitlab/dup.git"},
        )
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_disable_and_enable():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/config/repositories",
            json={"repo_url": "http://gitlab/toggle.git"},
        )

        # Disable
        resp = await client.post("/api/v1/config/repositories/toggle.git/disable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

        # Enable
        resp = await client.post("/api/v1/config/repositories/toggle.git/enable")
        assert resp.status_code == 200
        assert resp.json()["status"] == "enabled"


@pytest.mark.asyncio
async def test_disable_nonexistent():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/config/repositories/nonexistent/disable")
        assert resp.status_code == 404
