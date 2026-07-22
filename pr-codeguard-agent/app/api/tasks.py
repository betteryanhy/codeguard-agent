from datetime import datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.storage import StorageService, TaskRecord
from app.models.task import ScanTask

router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])
storage = StorageService()


@router.get("/")
async def list_tasks(skip: int = 0, limit: int = 50):
    """List scan tasks with pagination."""
    try:
        tasks = await storage.list_tasks(limit=limit, offset=skip)
        result = []
        for t in tasks:
            raw_findings = t.findings or []
            # Deduplicate at read time
            seen = set()
            deduped = []
            for f in raw_findings:
                key = (f.engine, f.file_path, f.line, f.message)
                if key not in seen:
                    seen.add(key)
                    deduped.append(f)
            by_severity = {"critical": 0, "major": 0, "minor": 0, "info": 0}
            for f in deduped:
                sev = (f.severity or "info").lower()
                if sev in by_severity:
                    by_severity[sev] += 1
            result.append({
                "id": t.id,
                "repo_url": t.repo_url,
                "mr_id": t.mr_id,
                "branch_name": t.source_branch or "main",
                "status": t.status,
                "total_findings": len(deduped),
                "summary": {"by_severity": by_severity},
                "created_at": t.created_at.isoformat() if t.created_at else None,
            })
        return result
    except Exception as e:
        return {"error": str(e), "tasks": []}


@router.get("/stats")
async def task_stats():
    """Return task statistics: total count, count by status, today's scan count."""
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        async with AsyncSession(storage.engine) as session:
            # Total count
            total_result = await session.execute(select(func.count(TaskRecord.id)))
            total = total_result.scalar() or 0

            # Group by status
            status_result = await session.execute(
                select(TaskRecord.status, func.count(TaskRecord.id))
                .group_by(TaskRecord.status)
            )
            by_status = dict(status_result.all())

            # Today's count
            today_result = await session.execute(
                select(func.count(TaskRecord.id))
                .where(TaskRecord.created_at >= today_start)
            )
            today_count = today_result.scalar() or 0

        return {
            "total": total,
            "by_status": by_status,
            "today_scans": today_count,
            "today_count": today_count,
            "today": today_count,
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """Retry a failed task by re-running the scan logic."""
    task = await storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ("failed", "error"):
        raise HTTPException(status_code=400, detail=f"Cannot retry task with status '{task.status}'")

    # Reset task status and re-run scan
    task.status = "pending"
    task.error_message = ""
    await storage.save_task(task)

    try:
        from app.services.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        result = await orchestrator.run_scan(
            task=task,
            source_branch="main",
            target_branch="main",
            ai_enabled=False,
            tf_change_detection=False,
        )
        await storage.save_task(result)
        return {"message": "Task retry initiated", "task_id": task_id, "status": result.status}
    except Exception as e:
        task.status = "failed"
        task.error_message = str(e)
        await storage.save_task(task)
        return {"message": "Task retry failed", "task_id": task_id, "error": str(e)}


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Cancel a pending task."""
    task = await storage.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel task with status '{task.status}'")

    task.status = "cancelled"
    task.completed_at = datetime.utcnow()
    await storage.save_task(task)

    return {"message": "Task cancelled", "task_id": task_id, "status": task.status}
