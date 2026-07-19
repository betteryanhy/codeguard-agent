from fastapi import APIRouter
from app.services.storage import StorageService

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
storage = StorageService()


@router.get("/")
async def list_tasks(skip: int = 0, limit: int = 50):
    """List scan tasks with pagination."""
    try:
        tasks = await storage.list_tasks(limit=limit, offset=skip)
        return [
            {
                "id": t.id,
                "repo_url": t.repo_url,
                "mr_id": t.mr_id,
                "status": t.status,
                "total_findings": len(t.findings),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ]
    except Exception as e:
        return {"error": str(e), "tasks": []}
