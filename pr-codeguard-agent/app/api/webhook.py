import json
import hmac
import asyncio
import logging
from fastapi import APIRouter, Request, HTTPException
from app.config import settings
from app.models.task import ScanTask
from app.utils.helpers import generate_task_id
from app.services.storage import StorageService

_storage = StorageService()

async def _store_task(task):
    """Persist task to storage."""
    await _storage.save_task(task)

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
        source_branch=source_branch,
        status="pending",
    )
    await _store_task(task)

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

    Uses Orchestrator directly for scan, then posts comment via GitLab.
    """
    try:
        if not should_scan:
            task.status = "completed"
            await _store_task(task)
            return

        # Get changed files from GitLab
        diff_files = None
        try:
            from app.services.gitlab_client import GitLabClient
            client = GitLabClient()
            mr_changes = client.get_mr_changes(repo_url, mr_id)
            diff_files = [c.get("new_path", "") for c in mr_changes.get("changes", []) if c.get("new_path")]
            logger.info(f"[{task.id}] MR changes: {len(diff_files)} files")
        except Exception as e:
            logger.warning(f"[{task.id}] Failed to get MR changes: {e}")

        # Run scan directly via Orchestrator
        from app.services.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        result = await orchestrator.run_scan(
            task=task,
            source_branch=source_branch,
            target_branch=target_branch,
            diff_files=diff_files,
            ai_enabled=False,
            tf_change_detection=False,
        )

        task = result
        await _store_task(task)
        logger.info(f"[{task.id}] Scan completed: {len(task.findings)} findings")

        # Analyze Terraform changes from raw diffs
        tf_analysis = None
        try:
            from app.services.gitlab_client import GitLabClient
            gc = GitLabClient()
            raw_diffs = gc.get_mr_raw_diffs(repo_url, mr_id)
            if raw_diffs:
                from app.engine.tf_diff_analyzer import analyze_tf_changes
                tf_analysis = analyze_tf_changes(raw_diffs)
                if tf_analysis and tf_analysis.get("has_tf_changes"):
                    logger.info(f"[{task.id}] Detected {len(tf_analysis['added_resources'])} added, "
                                f"{len(tf_analysis['removed_resources'])} removed, "
                                f"{len(tf_analysis['modified_resources'])} modified TF resources")
        except Exception as e:
            logger.warning(f"[{task.id}] Failed to analyze TF changes: {e}")

        # Post comment to MR (always post, even with 0 findings)
        try:
            from app.services.comment_builder import CommentBuilder
            builder = CommentBuilder()
            comment = builder.build_review(task.findings, tf_analysis=tf_analysis)
            if comment:
                gc = GitLabClient()
                gc.cleanup_bot_comments(repo_url, mr_id)
                gc.post_mr_comment(repo_url, mr_id, comment)
        except Exception as e:
            logger.warning(f"[{task.id}] Failed to post comment: {e}")

    except Exception as e:
        logger.error(f"[{task.id}] Scan execution failed: {e}")
        task.status = "failed"
        task.error_message = str(e)
        await _store_task(task)
