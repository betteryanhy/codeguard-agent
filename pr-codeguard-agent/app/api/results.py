from fastapi import APIRouter, HTTPException
from app.models.task import ScanTask
from app.services.storage import StorageService

router = APIRouter(prefix="/api/v1/results", tags=["results"])

storage = StorageService()

# Keep in-memory store temporarily for webhook compatibility
_tasks: dict[str, ScanTask] = {}


def store_task(task: ScanTask):
    """Store task in both memory and persistent storage."""
    _tasks[task.id] = task
    # Try persistent save (best effort) — only schedule on a running loop
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            loop.create_task(storage.save_task(task))
    except (RuntimeError, Exception):
        # No running loop (background thread after asyncio.run finishes) — skip
        pass


def get_task(task_id: str) -> ScanTask | None:
    """Get task from memory first, fall back to storage."""
    if task_id in _tasks:
        return _tasks[task_id]
    # Try storage (sync wrapper around async)
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        return loop.run_until_complete(storage.get_task(task_id))
    except (RuntimeError, Exception):
        return None


@router.get("/{task_id}")
async def get_results(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/{task_id}/summary")
async def get_summary(task_id: str):
    task = get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    severity_order = ["blocker", "critical", "major", "minor", "info"]
    return {
        "task_id": task.id,
        "status": task.status,
        "total_findings": len(task.findings),
        "grouped": {
            s: len([f for f in task.findings if f.severity == s])
            for s in severity_order
        },
    }


@router.get("/")
async def list_tasks(skip: int = 0, limit: int = 50):
    """List recent scan tasks."""
    try:
        import asyncio
        loop = asyncio.get_event_loop()
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
        return {"error": str(e), "tasks": list(_tasks.values())[skip:skip + limit]}
