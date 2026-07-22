"""GitLab Events Webhook - receives push, MR, and branch events.

This endpoint receives GitLab Push Events, Merge Request Events, and
other repository-level webhook events. It stores them in the knowledge
base for later querying via the Q&A system.

Configure your GitLab project to send Push Events and MR Events to:
  POST /api/v1/hooks/gitlab-events

For branch events, configure GitLab System Hooks to send to:
  POST /api/v1/system-hooks/gitlab
"""

import json
import logging
from fastapi import APIRouter, HTTPException, Request

from app.services.event_processor import EventProcessor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/hooks", tags=["events_webhook"])

# Singleton event processor (shared across requests)
_processor: EventProcessor | None = None


def get_processor() -> EventProcessor:
    global _processor
    if _processor is None:
        _processor = EventProcessor()
    return _processor


@router.post("/gitlab-events")
async def receive_gitlab_event(request: Request):
    """Receive GitLab Push/MR/Branch webhook events.

    GitLab sends:
      - Push events with object_kind="push"
      - MR events with object_kind="merge_request"
      - Tag push events with object_kind="tag_push"

    All events are processed and stored in the knowledge base.
    """
    body = await request.body()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Determine event type
    # GitLab webhooks use "object_kind", system hooks use "event_type"
    event_type = payload.get("object_kind") or payload.get("event_type", "unknown")

    processor = get_processor()
    await processor.process(event_type, payload)

    return {
        "status": "accepted",
        "event": event_type,
    }


@router.get("/gitlab-events/branch-events")
async def list_branch_events(
    project_path: str = "",
    branch: str = "",
    limit: int = 20,
):
    """List recent branch create/delete events from in-memory store."""
    processor = get_processor()
    events = processor.get_branch_events(
        project_path=project_path,
        branch=branch,
        limit=limit,
    )
    return {
        "total": len(events),
        "events": [
            {
                "project_path": e.project_path,
                "branch": e.branch,
                "action": e.action,
                "actor": e.actor,
                "timestamp": e.timestamp.isoformat(),
            }
            for e in events
        ],
    }
