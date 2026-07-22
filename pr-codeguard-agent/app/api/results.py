import logging
from fastapi import APIRouter, HTTPException
from app.models.task import ScanTask
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/results", tags=["results"])

storage = StorageService()


# Kept for backward compatibility: webhook.py imports this.
# Task persistence is handled via StorageService internally.
async def store_task(task: ScanTask):
    """Persist a scan task to storage."""
    await storage.save_task(task)


def _resolve_findings(task: ScanTask) -> list:
    """Extract findings from a task as serializable dicts, deduplicated."""
    findings = task.findings or []
    seen = set()
    deduped = []
    for f in findings:
        key = (f.engine, f.file_path, f.line, f.message)
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return [
        {
            "severity": f.severity,
            "engine": f.engine,
            "message": f.message,
            "file_path": f.file_path,
            "line": f.line,
            "code_snippet": getattr(f, "code_snippet", ""),
            "recommendation": getattr(f, "recommendation", ""),
            "rule_id": getattr(f, "rule_id", ""),
        }
        for f in deduped
    ]


def _task_to_dict(task: ScanTask) -> dict:
    """Serialize a ScanTask for API response."""
    findings = _resolve_findings(task)
    by_severity = {"critical": 0, "major": 0, "minor": 0, "info": 0}
    for f in findings:
        sev = (f.get("severity") or "info").lower()
        if sev in by_severity:
            by_severity[sev] += 1
    return {
        "id": task.id,
        "repo_url": task.repo_url,
        "mr_id": task.mr_id,
        "mr_title": task.mr_title or "",
        "branch_name": task.source_branch or "main",
        "status": task.status,
        "total_findings": len(findings),
        "summary": {"by_severity": by_severity},
        "findings": findings,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "error_message": task.error_message or "",
    }


@router.get("/{task_id}")
async def get_results(task_id: str):
    """Get full task results including findings from persistent storage."""
    try:
        task = await storage.get_task(task_id)
    except Exception as e:
        logger.warning("Storage lookup failed for task %s: %s", task_id, e)
        task = None

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_to_dict(task)


@router.get("/{task_id}/summary")
async def get_summary(task_id: str):
    """Get a lightweight summary of task results."""
    try:
        task = await storage.get_task(task_id)
    except Exception as e:
        logger.warning("Storage lookup failed for task %s: %s", task_id, e)
        task = None

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    severity_order = ["blocker", "critical", "major", "minor", "info"]
    findings = task.findings or []
    return {
        "task_id": task.id,
        "status": task.status,
        "total_findings": len(findings),
        "grouped": {
            s: len([f for f in findings if f.severity == s])
            for s in severity_order
        },
    }
