"""Auto-discovery API - trigger scan, list projects, manage webhooks."""

import asyncio
import logging
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/discovery", tags=["discovery"])


def _get_discovery(request: Request):
    """Get discovery service from app state."""
    svc = getattr(request.app.state, "discovery_service", None)
    if not svc:
        raise HTTPException(status_code=503, detail="Discovery service not initialized")
    return svc


@router.post("/scan")
async def trigger_scan(request: Request):
    """Trigger a full scan of all GitLab projects.

    Scans all projects accessible via the configured GitLab API token
    and caches them for webhook registration.
    """
    svc = _get_discovery(request)

    loop = asyncio.get_event_loop()
    projects = await loop.run_in_executor(None, svc.scan_all)

    return {
        "status": "completed",
        "total": len(projects),
        "projects": [
            {
                "project_id": p.project_id,
                "name": p.name_with_namespace,
                "visibility": p.visibility,
            }
            for p in projects
        ],
    }


@router.post("/register-webhooks")
async def register_webhooks(request: Request):
    """Ensure webhooks exist for all discovered projects.

    Checks each project for an existing webhook pointing to this agent.
    Creates one if missing. Only subscribes to merge_request_events.
    """
    svc = _get_discovery(request)

    loop = asyncio.get_event_loop()
    stats = await loop.run_in_executor(None, svc.ensure_webhooks)

    return {"status": "completed", "stats": stats}


@router.get("/projects")
async def list_projects(request: Request):
    """List all discovered projects with webhook status."""
    svc = _get_discovery(request)
    projects = svc.list_discovered()

    return {
        "total": len(projects),
        "projects": projects,
    }


@router.post("/projects/{project_id}/register")
async def register_single_webhook(request: Request, project_id: int):
    """Register webhook for a single project by its GitLab project ID."""
    svc = _get_discovery(request)

    project = svc.get_project_by_id(project_id)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found in discovered list")

    loop = asyncio.get_event_loop()
    ok = await loop.run_in_executor(None, svc.ensure_single_webhook, project_id)

    return {
        "status": "ok" if ok else "failed",
        "project": project.name_with_namespace,
        "project_id": project_id,
        "webhook_url": project.webhook_url if project.registered else "",
        "registered": project.registered,
    }


# ------------------------------------------------------------------
# Webhook Health Monitoring
# ------------------------------------------------------------------


def _get_health_checker(request: Request):
    """Get webhook health checker from app state."""
    checker = getattr(request.app.state, "webhook_health_checker", None)
    if not checker:
        raise HTTPException(status_code=503, detail="Webhook health checker not initialized")
    return checker


@router.get("/webhook-health")
async def list_webhook_health(request: Request):
    """List webhook health status for all discovered projects.

    Returns current cached health status. Use POST /webhook-health/check
    to trigger a fresh check.
    """
    checker = _get_health_checker(request)
    results = checker.list_health()
    summary = checker.get_health_summary()

    # If cache is empty, return a more helpful message
    if not results:
        return {
            "summary": {"total": 0, "healthy": 0, "broken": 0, "health_rate": 0},
            "message": "No health data yet. Use POST /api/v1/discovery/webhook-health/check to run first check.",
            "results": [],
        }

    return {"summary": summary, "results": results}


@router.post("/webhook-health/check")
async def trigger_webhook_health_check(request: Request):
    """Trigger an immediate webhook health check.

    Checks each registered webhook's recent delivery status on GitLab.
    Auto-repairs any webhooks that show 3+ consecutive delivery failures.
    """
    from app.services.discovery_service import DiscoveryService
    from app.services.webhook_health import WebhookHealthChecker

    # Get projects
    svc = _get_discovery(request)
    projects = svc.list_discovered()

    if not projects:
        return {
            "status": "completed",
            "checked": 0,
            "healthy": 0,
            "broken": 0,
            "auto_fixed": 0,
            "message": "No discovered projects to check",
        }

    # Run health check
    loop = asyncio.get_event_loop()
    checker = WebhookHealthChecker()
    results = await loop.run_in_executor(None, checker.check_all, projects)

    # Cache for the GET endpoint
    request.app.state.webhook_health_checker = checker

    summary = checker.get_health_summary()

    return {
        "status": "completed",
        "checked": len(results),
        "healthy": summary["healthy"],
        "broken": summary["broken"],
        "auto_fixed": summary["auto_fixed"],
        "health_rate": summary["health_rate"],
        "results": checker.list_health(),
    }
