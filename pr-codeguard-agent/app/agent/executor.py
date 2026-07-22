"""Tool executor: runs the planned tool calls in sequence."""

import logging
from typing import Any

from app.tools.base import BaseTool, ToolResult
from app.tools.scanner import ScannerTool
from app.tools.gitlab_commenter import GitLabCommenterTool
from app.tools.baseline_builder import BaselineBuilderTool
from app.tools.diff_analyzer import DiffAnalyzerTool
from app.tools.knowledge_writer import KnowledgeWriterTool
from app.tools.knowledge_reader import KnowledgeReaderTool
from app.tools.diff_fetcher import DiffFetcherTool

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Discovers and executes tools by name."""

    def __init__(self, strategy_mgr: object = None):
        self._tools: dict[str, BaseTool] = {}
        self._strategy_mgr = strategy_mgr
        self._register_defaults()

    def _register_defaults(self):
        """Register built-in tools."""
        self.register(ScannerTool(strategy_mgr=self._strategy_mgr))
        self.register(GitLabCommenterTool())
        self.register(BaselineBuilderTool())
        self.register(DiffAnalyzerTool())
        self.register(KnowledgeWriterTool())
        self.register(KnowledgeReaderTool())
        self.register(DiffFetcherTool())

    def register(self, tool: BaseTool):
        """Register a tool by its name."""
        self._tools[tool.name] = tool
        logger.debug("Registered tool: %s", tool.name)

    def get_tool(self, name: str) -> BaseTool | None:
        """Look up a registered tool by name."""
        return self._tools.get(name)

    async def execute_step(self, step: dict) -> tuple[str, ToolResult]:
        """Execute a single plan step.

        Args:
            step: {"tool": "name", "params": {...}}

        Returns:
            Tuple of (tool_name, ToolResult)
        """
        tool_name = step.get("tool", "")
        params = step.get("params", {})

        tool = self.get_tool(tool_name)
        if not tool:
            logger.warning("Unknown tool: %s", tool_name)
            return tool_name, ToolResult.fail(f"Unknown tool: {tool_name}")

        try:
            logger.info("Executing tool: %s with params: %s", tool_name, params)
            result = await tool.execute(**params)
            logger.info("Tool %s completed: success=%s", tool_name, result.success)
            return tool_name, result
        except Exception as e:
            logger.error("Tool %s raised exception: %s", tool_name, e)
            return tool_name, ToolResult.fail(str(e))

    async def execute_plan(self, plan: list[dict]) -> dict[str, ToolResult]:
        """Execute all steps in a plan sequentially.

        Args:
            plan: List of {"tool": "...", "params": {...}}

        Returns:
            Dict mapping tool names to their ToolResult
        """
        results: dict[str, Any] = {}

        for step in plan:
            tool_name, result = await self.execute_step(step)
            results[tool_name] = result

            # If a critical tool fails, stop the plan
            if not result.success and tool_name in ("run_scanners",):
                logger.error("Critical tool %s failed, stopping plan", tool_name)
                break

        return results
