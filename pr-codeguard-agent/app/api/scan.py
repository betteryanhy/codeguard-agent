"""Manual scan trigger endpoints."""
import asyncio
import logging
import re
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.storage import StorageService
from app.models.task import ScanTask
from app.utils.helpers import generate_task_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scan", tags=["scan"])


class ScanRepoRequest(BaseModel):
    repo_url: str
    branch: str = ""


@router.post("/repo")
async def scan_repo(body: ScanRepoRequest):
    """Scan a single repository.

    Clones the repo and runs all enabled engines.
    Returns findings immediately after scan completes.
    """
    if not body.repo_url.strip():
        raise HTTPException(status_code=400, detail="repo_url is required")

    # Normalize repo URL: remove trailing .git
    normalized_url = re.sub(r'\.git$', '', body.repo_url.strip())

    from app.services.orchestrator import Orchestrator
    from app.services.discovery_service import DiscoveryService

    # Resolve the project to get default branch
    discovery = DiscoveryService()
    project = discovery.get_project_by_url(normalized_url)
    branch = body.branch or (project.default_branch if project else "main")

    # Create a scan task
    task_id = generate_task_id()
    task = ScanTask(
        id=task_id,
        repo_url=normalized_url,
        mr_id=0,
        mr_title="Manual scan",
        source_branch=branch,
        status="pending",
        created_at=datetime.utcnow(),
    )

    # Save initial pending state
    storage = StorageService()
    await storage.save_task(task)

    # Run scan
    orchestrator = Orchestrator()
    result = await orchestrator.run_scan(
        task=task,
        source_branch=branch,
        target_branch=branch,
        ai_enabled=False,
        tf_change_detection=False,
    )

    # Save completed state
    await storage.save_task(result)

    logger.info("Manual scan completed for %s: %d findings", body.repo_url, len(result.findings))

    # Build summary
    by_severity = {"critical": 0, "major": 0, "minor": 0, "info": 0}
    for f in result.findings:
        sev = f.severity.lower()
        if sev in by_severity:
            by_severity[sev] += 1

    return {
        "task_id": task_id,
        "status": result.status,
        "findings_count": len(result.findings),
        "by_severity": by_severity,
        "branch": branch,
        "findings": [
            {
                "severity": f.severity,
                "engine": f.engine,
                "message": f.message,
                "file_path": f.file_path,
                "line": f.line,
            }
            for f in result.findings
        ],
    }


@router.post("/all")
async def scan_all():
    """Scan all discovered projects.

    Iterates over all discovered projects and runs a scan on each.
    Returns a summary of results.
    """
    from app.services.discovery_service import DiscoveryService
    from app.services.orchestrator import Orchestrator
    from app.services.storage import StorageService
    from app.utils.helpers import generate_task_id

    discovery = DiscoveryService()
    # Ensure discovery data is loaded by scanning GitLab
    projects = discovery.list_discovered()
    if not projects:
        # Try to scan GitLab first
        try:
            discovery.scan_all()
            projects = discovery.list_discovered()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"No projects discovered and discovery failed: {e}")

    if not projects:
        return {"results": [], "total": 0}

    storage = StorageService()
    orchestrator = Orchestrator()
    results = []

    for proj in projects:
        repo_url = proj.get("http_url_to_repo", "") if isinstance(proj, dict) else getattr(proj, "http_url_to_repo", "")
        repo_url = re.sub(r'\.git$', '', repo_url)
        default_branch = proj.get("default_branch", "main") if isinstance(proj, dict) else getattr(proj, "default_branch", "main")

        if not repo_url:
            continue

        try:
            task_id = generate_task_id()
            task = ScanTask(
                id=task_id,
                repo_url=repo_url,
                mr_id=0,
                mr_title="Scheduled scan",
                source_branch=default_branch,
                status="pending",
                created_at=datetime.utcnow(),
            )
            await storage.save_task(task)

            result = await orchestrator.run_scan(
                task=task,
                source_branch=default_branch,
                target_branch=default_branch,
                ai_enabled=False,
                tf_change_detection=False,
            )
            await storage.save_task(result)

            results.append({
                "repo_url": repo_url,
                "task_id": task_id,
                "findings_count": len(result.findings),
                "status": result.status,
            })
            logger.info("Scanned %s: %d findings", repo_url, len(result.findings))
        except Exception as e:
            logger.error("Scan failed for %s: %s", repo_url, e)
            results.append({
                "repo_url": repo_url,
                "task_id": "",
                "findings_count": 0,
                "status": "failed",
                "error": str(e),
            })

    return {"results": results, "total": len(results)}
