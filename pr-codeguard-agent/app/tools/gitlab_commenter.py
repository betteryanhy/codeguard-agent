"""Tool to post comments to GitLab Merge Requests."""

import logging

from app.tools.base import BaseTool, ToolResult
from app.services.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


class GitLabCommenterTool(BaseTool):
    """Post a review comment to a GitLab MR."""

    @property
    def name(self) -> str:
        return "write_comment"

    async def execute(
        self,
        repo_url: str = "",
        mr_id: int = 0,
        body: str = "",
        **kwargs,
    ) -> ToolResult:
        """Post a comment to the specified MR.

        Args:
            repo_url: Git repository URL
            mr_id: Merge Request ID
            body: Comment text (Markdown)

        Returns:
            ToolResult with API response
        """
        if not body:
            return ToolResult.fail("Comment body is empty")

        try:
            client = GitLabClient()
            response = client.post_mr_comment(repo_url, mr_id, body)
            logger.info("Comment posted to MR !%d", mr_id)
            return ToolResult.ok(response)
        except Exception as e:
            logger.error("Failed to post MR comment: %s", e)
            return ToolResult.fail(str(e))
