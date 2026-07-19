import json
import hmac
import asyncio
import logging
from fastapi import APIRouter, Request, HTTPException
from app.config import settings
from app.models.task import ScanTask
from app.utils.helpers import generate_task_id
from app.api.results import store_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhook", tags=["webhook"])


@router.post("/gitlab")
async def handle_gitlab_webhook(request: Request):
    """Receive GitLab Merge Request webhook events."""
    body = await request.body()

    # Verify webhook secret if configured
    if settings.webhook_secret:
        token = request.headers.get("X-Gitlab-Token", "")
        if not token or not hmac.compare_digest(token, settings.webhook_secret):
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    payload = json.loads(body)
    event_type = request.headers.get("X-Gitlab-Event", "")

    # Only process Merge Request events
    if event_type != "Merge Request Hook":
        return {"status": "ignored", "reason": f"unsupported event: {event_type}"}

    mr_data = payload.get("object_attributes", {})
    action = mr_data.get("action")
    mr_id = mr_data.get("iid")

    # Extract user info from payload
    user_data = payload.get("user", {})
    author = user_data.get("name", "") or mr_data.get("author", {}).get("name", "")

    # Process both open/update events and merge events
    if action in ("open", "reopen", "update"):
        # Full scan: detect issues, record commits and knowledge
        should_scan = True
    elif action == "merge":
        # Merge event: record merge info without re-scanning
        should_scan = False
    else:
        return {"status": "ignored", "reason": f"action: {action}"}

    repo_url = (
        payload.get("project", {}).get("git_http_url") or
        payload.get("project", {}).get("http_url") or
        ""
    )

    if not repo_url:
        raise HTTPException(status_code=400, detail="Repository URL not found in payload")

    source_branch = mr_data.get("source_branch", "")
    target_branch = mr_data.get("target_branch", "")

    task_id = generate_task_id()

    task = ScanTask(
        id=task_id,
        repo_url=repo_url,
        mr_id=mr_id,
        mr_title=mr_data.get("title", ""),
        status="pending",
    )
    store_task(task)

    # Get strategy manager from app state
    strategy_mgr = getattr(request.app.state, "scan_strategy_manager", None)

    # Fire-and-forget: run scan in thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        None, _execute_scan_sync,
        task, repo_url, mr_id, source_branch, target_branch,
        author, should_scan, strategy_mgr,
    )

    return {
        "status": "accepted",
        "task_id": task_id,
        "mr_id": mr_id,
    }


def _execute_scan_sync(
    task: ScanTask,
    repo_url: str,
    mr_id: int,
    source_branch: str,
    target_branch: str,
    author: str = "",
    should_scan: bool = True,
    strategy_mgr: object = None,
):
    """Run scan pipeline in a separate thread (sync wrapper)."""
    import asyncio as _asyncio
    try:
        _asyncio.run(
            _execute_scan(task, repo_url, mr_id, source_branch, target_branch, author, should_scan, strategy_mgr),
        )
    except Exception as e:
        logger.error(f"[{task.id}] Scan thread failed: {e}")


async def _execute_scan(
    task: ScanTask,
    repo_url: str,
    mr_id: int,
    source_branch: str,
    target_branch: str,
    author: str = "",
    should_scan: bool = True,
    strategy_mgr: object = None,
):
    """Run scan pipeline and post comment asynchronously.

    Uses AgentBrain for decision-making and tool orchestration,
    with fallback to the original hard-coded pipeline.
    """
    try:
        from app.services.gitlab_client import GitLabClient

        # Get changed files from GitLab
        diff_files = None
        try:
            client = GitLabClient()
            mr_changes = client.get_mr_changes(repo_url, mr_id)
            diff_files = [c.get("new_path", "") for c in mr_changes.get("changes", []) if c.get("new_path")]
            logger.info(f"[{task.id}] MR changes: {len(diff_files)} files")
        except Exception as e:
            logger.warning(f"[{task.id}] Failed to get MR changes: {e}")

        # Use AgentBrain to process the MR event (with strategy config)
        from app.agent.brain import AgentBrain
        brain = AgentBrain(strategy_mgr=strategy_mgr)
        result = await brain.process_mr_event(
            task_id=task.id,
            repo_url=repo_url,
            mr_id=mr_id,
            source_branch=source_branch,
            target_branch=target_branch,
            mr_title=task.mr_title,
            diff_files=diff_files,
            author=author,
            should_scan=should_scan,
        )

        # Update task with findings
        task.findings = result.get("findings", [])
        task.status = "completed"
        task.completed_at = __import__("datetime").datetime.utcnow()
        store_task(task)
        logger.info(f"[{task.id}] AgentBrain completed: {result.get('findings_count', 0)} findings")

    except Exception as e:
        logger.error(f"[{task.id}] Scan execution failed: {e}")
        task.status = "failed"
        task.error_message = str(e)
        store_task(task)
