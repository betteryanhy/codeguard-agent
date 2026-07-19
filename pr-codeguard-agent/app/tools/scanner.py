"""Tool wrapping the existing scan engines (Orchestrator)."""

import asyncio
import logging

from app.config import settings
from app.tools.base import BaseTool, ToolResult
from app.models.task import ScanTask
from app.services.orchestrator import Orchestrator
from app.services.repo_manager import RepoManager

logger = logging.getLogger(__name__)


class ScannerTool(BaseTool):
    """Run code scan engines on a repository branch."""

    def __init__(self, strategy_mgr: object = None):
        super().__init__()
        self._strategy_mgr = strategy_mgr

    def _get_strategy(self, repo_url: str) -> object:
        """Get scan strategy for this repo, or None to use defaults."""
        if self._strategy_mgr:
            try:
                return self._strategy_mgr.get_strategy(repo_url)
            except Exception:
                pass
        return None

    @property
    def name(self) -> str:
        return "run_scanners"

    async def execute(
        self,
        task_id: str = "",
        repo_url: str = "",
        mr_id: int = 0,
        source_branch: str = "",
        target_branch: str = "",
        diff_files: list[str] | None = None,
        **kwargs,
    ) -> ToolResult:
        """Run all enabled scan engines on the given repository branch.

        Args:
            task_id: Unique task identifier
            repo_url: Git repository URL
            mr_id: Merge Request ID
            source_branch: Source branch to scan
            target_branch: Target branch for diff comparison
            diff_files: Optional list of changed file paths

        Returns:
            ToolResult with list of findings
        """
        try:
            task = ScanTask(
                id=task_id,
                repo_url=repo_url,
                mr_id=mr_id,
                status="pending",
            )

            # Apply scan strategy if available
            strategy = self._get_strategy(repo_url)
            enabled_engines = None
            enable_ai = None
            enable_tf = True

            if strategy:
                enabled_engines = [
                    name for name, enabled in strategy.engines_enabled.items()
                    if enabled
                ]
                enable_ai = strategy.ai_enabled
                enable_tf = strategy.tf_change_detection
                logger.info(
                    "Applying strategy for %s: engines=%s, ai=%s, tf=%s",
                    repo_url, enabled_engines, enable_ai, enable_tf,
                )

            orchestrator = Orchestrator()
            result = await orchestrator.run_scan(
                task=task,
                source_branch=source_branch,
                target_branch=target_branch,
                diff_files=diff_files,
                enabled_engines=enabled_engines,
                ai_enabled=enable_ai,
                tf_change_detection=enable_tf,
            )

            logger.info(
                "ScannerTool: %d findings from %s MR !%d",
                len(result.findings or []),
                repo_url,
                mr_id,
            )
            return ToolResult.ok(result)

        except Exception as e:
            logger.error("ScannerTool failed: %s", e)
            return ToolResult.fail(str(e))
