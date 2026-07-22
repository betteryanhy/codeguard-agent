import time
import logging

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/system", tags=["system"])
_start_time = time.time()

logger = logging.getLogger(__name__)


@router.get("/health")
async def deep_health():
    """Deep health check endpoint."""
    checks = {
        "status": "ok",
        "uptime_seconds": int(time.time() - _start_time),
        "checks": {},
    }

    # 1. Database check
    try:
        from app.services.storage import StorageService
        s = StorageService()
        tasks = await s.list_tasks(limit=1)
        checks["checks"]["database"] = {"status": "ok"}
    except Exception as e:
        checks["checks"]["database"] = {"status": "error", "error": str(e)}
        checks["status"] = "degraded"

    # 2. Trivy check
    try:
        from app.engine.trivy_scanner import find_trivy
        import os
        from app.config import settings
        trivy_path = find_trivy()
        trivy_info = {
            "available": trivy_path is not None,
            "path": trivy_path or "",
        }
        if trivy_path:
            trivy_cache = os.path.abspath(settings.trivy_cache_dir)
            db_file = os.path.join(trivy_cache, "db", "trivy.db")
            trivy_info["db_ok"] = os.path.isfile(db_file)
        checks["checks"]["trivy"] = trivy_info
        if not trivy_path:
            checks["checks"]["trivy"]["status"] = "unavailable"
        else:
            checks["checks"]["trivy"]["status"] = "ok"
    except Exception as e:
        checks["checks"]["trivy"] = {"status": "error", "error": str(e)}
        checks["status"] = "degraded"

    # 3. GitLab check
    try:
        from app.services.gitlab_client import GitLabClient
        client = GitLabClient()
        projects = client.list_projects(per_page=1)
        checks["checks"]["gitlab"] = {"status": "ok", "available": True}
    except Exception as e:
        checks["checks"]["gitlab"] = {"status": "error", "error": str(e)}
        checks["degraded_reasons"] = checks.get("degraded_reasons", []) + [f"GitLab: {str(e)[:50]}"]

    # 4. Knowledge base check
    try:
        from app.main import knowledge_base
        if knowledge_base:
            checks["checks"]["knowledge_base"] = {"status": "ok"}
        else:
            checks["checks"]["knowledge_base"] = {"status": "disabled"}
    except Exception as e:
        checks["checks"]["knowledge_base"] = {"status": "error", "error": str(e)}
        checks["degraded_reasons"] = checks.get("degraded_reasons", []) + [f"KB: {str(e)[:50]}"]

    # Override: if DB and Trivy are fine, mark as ok (GitLab issues are only degraded)
    db_ok = checks["checks"].get("database", {}).get("status") == "ok"
    trivy_ok = checks["checks"].get("trivy", {}).get("status") == "ok"
    if db_ok and trivy_ok:
        checks["status"] = "ok"

    return checks
