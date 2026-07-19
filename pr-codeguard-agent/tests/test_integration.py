"""Integration tests for PR-CodeGuard Agent."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_full_flow_webhook_to_results():
    """Test the complete flow: webhook accept → check results."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Step 1: Send webhook
        resp = await client.post(
            "/api/v1/webhook/gitlab",
            json={
                "object_kind": "merge_request",
                "object_attributes": {
                    "iid": 100,
                    "title": "test: integration",
                    "action": "open",
                    "source_branch": "feature",
                    "target_branch": "main",
                },
                "project": {"git_http_url": "http://gitlab/test/integration.git"},
            },
            headers={
                "X-Gitlab-Event": "Merge Request Hook",
                "X-Gitlab-Token": "guard-secret",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        task_id = data["task_id"]

        # Step 2: Register config
        resp = await client.post(
            "/api/v1/config/repositories",
            json={"repo_url": "http://gitlab/test/integration.git"},
        )
        assert resp.status_code == 200

        # Step 3: List configs
        resp = await client.get("/api/v1/config/repositories")
        assert resp.status_code == 200
        repos = resp.json()
        assert len(repos) >= 1
