import json
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def mr_payload_open():
    return {
        "object_kind": "merge_request",
        "object_attributes": {
            "iid": 42,
            "title": "feat: add user export",
            "action": "open",
            "source_branch": "feat-export",
            "target_branch": "main",
        },
        "project": {
            "git_http_url": "http://gitlab/root/test-project.git",
        },
    }


@pytest.mark.asyncio
async def test_webhook_accepts_mr_open(mr_payload_open):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/webhook/gitlab",
            json=mr_payload_open,
            headers={
                "X-Gitlab-Event": "Merge Request Hook",
                "X-Gitlab-Token": "guard-secret",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"
        assert "task_id" in data
        assert data["mr_id"] == 42


@pytest.mark.asyncio
async def test_webhook_ignores_wrong_event():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/webhook/gitlab",
            json={},
            headers={
                "X-Gitlab-Event": "Push Hook",
                "X-Gitlab-Token": "guard-secret",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_ignores_close_action():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/webhook/gitlab",
            json={
                "object_kind": "merge_request",
                "object_attributes": {"iid": 43, "action": "close"},
                "project": {"git_http_url": "http://gitlab/root/test.git"},
            },
            headers={
                "X-Gitlab-Event": "Merge Request Hook",
                "X-Gitlab-Token": "guard-secret",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


@pytest.mark.asyncio
async def test_webhook_results_created(mr_payload_open):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Send webhook
        resp = await client.post(
            "/api/v1/webhook/gitlab",
            json=mr_payload_open,
            headers={
                "X-Gitlab-Event": "Merge Request Hook",
                "X-Gitlab-Token": "guard-secret",
            },
        )
        task_id = resp.json()["task_id"]
        
        # Check results
        resp2 = await client.get(f"/api/v1/results/{task_id}")
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "pending"
