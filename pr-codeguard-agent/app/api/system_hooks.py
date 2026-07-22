"""GitLab System Hooks API - real-time project create/delete notifications.

GitLab System Hooks are admin-level webhooks that notify about global events
(project create/destroy, user create, etc.). This module receives them and
keeps the agent's project list in sync with GitLab automatically.
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.services.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/system-hooks", tags=["system_hooks"])


def _get_discovery(request: Request):
    """Get discovery service from app state."""
    svc = getattr(request.app.state, "discovery_service", None)
    if not svc:
        raise HTTPException(status_code=503, detail="Discovery service not initialized")
    return svc


# ------------------------------------------------------------------
# Event handlers
# ------------------------------------------------------------------


async def _handle_project_create(request: Request, event: dict):
    """A new project was created in GitLab."""
    svc = _get_discovery(request)
    project_id = event.get("project_id")
    path_with_namespace = event.get("path_with_namespace", "")

    if not project_id:
        logger.warning("System hook project_create missing project_id")
        return

    # Skip if already known
    existing = svc.get_project_by_id(project_id)
    if existing:
        logger.debug("Project %d already discovered, skipping", project_id)
        return

    logger.info("System hook: new project %d (%s)", project_id, path_with_namespace)

    # Fetch full project details from GitLab API and add to cache
    try:
        project = svc.add_project_by_id(project_id)
        if project:
            logger.info(
                "Auto-discovered new project: %s (ID=%d)",
                project.name_with_namespace, project_id,
            )
            # Auto-register webhook for the new project
            svc.ensure_single_webhook(project_id)
        else:
            logger.warning("Failed to fetch project %d details", project_id)
    except Exception as e:
        logger.warning("Failed to process project_create for %d: %s", project_id, e)


async def _handle_project_destroy(request: Request, event: dict):
    """A project was deleted from GitLab."""
    svc = _get_discovery(request)
    project_id = event.get("project_id")
    path_with_namespace = event.get("path_with_namespace", "")

    if not project_id:
        logger.warning("System hook project_destroy missing project_id")
        return

    existing = svc.get_project_by_id(project_id)
    if not existing:
        logger.debug("Project %d not in cache, nothing to remove", project_id)
        return

    svc.remove_project(project_id)
    logger.info(
        "Removed deleted project: %s (ID=%d)",
        path_with_namespace or existing.name_with_namespace, project_id,
    )


async def _handle_project_rename(request: Request, event: dict):
    """A project was renamed. Update our cache."""
    svc = _get_discovery(request)
    project_id = event.get("project_id")

    if not project_id:
        return

    existing = svc.get_project_by_id(project_id)
    if existing:
        # Refresh from GitLab API to get updated details
        try:
            svc.add_project_by_id(project_id)
            logger.info(
                "Updated renamed project %d: %s -> %s",
                project_id,
                existing.path_with_namespace,
                event.get("path_with_namespace", ""),
            )
        except Exception as e:
            logger.warning("Failed to refresh renamed project %d: %s", project_id, e)


async def _handle_project_transfer(request: Request, event: dict):
    """A project was transferred to another namespace."""
    await _handle_project_rename(request, event)


EVENT_HANDLERS = {
    "project_create": _handle_project_create,
    "project_destroy": _handle_project_destroy,
    "project_rename": _handle_project_rename,
    "project_transfer": _handle_project_transfer,
}


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post("/gitlab")
async def receive_system_hook(request: Request):
    """Receive GitLab System Hook events.

    GitLab sends POST requests with JSON body containing event_name and
    event-specific fields. We handle project_create, project_destroy,
    project_rename, and project_transfer events.
    """
    body = await request.body()
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_name = event.get("event_name", "")
    logger.debug("System hook received: event_name=%s", event_name)

    handler = EVENT_HANDLERS.get(event_name)
    if handler:
        await handler(request, event)
        return {"status": "ok", "event": event_name}
    else:
        logger.debug("Ignored system hook event: %s", event_name)
        return {"status": "ignored", "event": event_name}


@router.post("/setup")
async def setup_system_hook(request: Request):
    """Auto-register this agent's system hook URL in GitLab.

    Calls GitLab Admin API to register or update the system hook
    pointing to this agent.
    """
    svc = _get_discovery(request)

    # Determine the public URL for the system hook
    hook_url = f"{svc._agent_url.rstrip('/')}/api/v1/system-hooks/gitlab"

    client = GitLabClient()
    try:
        existing_hooks = client._list_system_hooks()
    except Exception as e:
        logger.warning("Cannot list system hooks (not supported?): %s", e)
        return {
            "status": "unsupported",
            "message": "GitLab system hooks API not available. "
                       "Your GitLab instance may not support system hooks, "
                       "or the API token lacks admin privileges. "
                       "Fallback: periodic background sync handles project changes.",
            "hook_url": hook_url,
        }

    # Check if already registered
    for h in existing_hooks:
        if h.get("url") == hook_url:
            return {
                "status": "already_registered",
                "hook_id": h["id"],
                "url": hook_url,
            }

    # Create new system hook
    try:
        result = client._create_system_hook(hook_url, settings.webhook_secret)
        logger.info("System hook registered: %s (ID=%s)", hook_url, result.get("id"))
        return {
            "status": "registered",
            "hook_id": result.get("id"),
            "url": hook_url,
        }
    except Exception as e:
        logger.warning("Failed to register system hook: %s", e)
        return {
            "status": "unsupported",
            "message": f"Cannot register system hook: {e}. "
                       "Fallback: periodic background sync handles project changes.",
            "hook_url": hook_url,
        }
