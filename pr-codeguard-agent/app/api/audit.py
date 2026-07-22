from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.api.auth import get_current_user, get_current_user_optional
from app.services.storage import StorageService, UserRecord

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])
storage = StorageService()


@router.get("/logs")
async def list_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: str = Query(""),
    resource_type: str = Query(""),
    current_user: Optional[UserRecord] = Depends(get_current_user_optional),
):
    """List audit logs with pagination and optional filters."""
    items, total = await storage.list_audit_logs(
        limit=limit, offset=offset,
        action=action or None,
        resource_type=resource_type or None,
    )
    return {"items": items, "total": total}
