"""Tool for semantic analysis of code diffs using LLM."""

import json
import logging
from typing import Optional

from app.config import settings
from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a code diff analyzer. Given a list of changed files and their content,
analyze the semantic meaning of the changes. Focus on:

1. What functionality was added/removed/modified?
2. What interfaces (API endpoints, functions, classes) were affected?
3. What modules/subsystems were touched?
4. Are there any security concerns or potential regressions?
5. Summarize in a way that would help a reviewer understand the intent.

Respond in JSON format:
{
  "summary": "Concise summary of changes",
  "interfaces_changed": ["interface1", "interface2"],
  "modules_affected": ["module1", "module2"],
  "risk_level": "low|medium|high",
  "risk_items": ["risk1", "risk2"],
  "security_concerns": ["concern1"] or []
}
"""


class DiffAnalyzerTool(BaseTool):
    """Analyze MR diffs semantically using LLM."""

    @property
    def name(self) -> str:
        return "semantic_analyze"

    async def execute(
        self,
        diff_files: Optional[list[str]] = None,
        changed_content: Optional[str] = None,
        mr_title: str = "",
        **kwargs,
    ) -> ToolResult:
        """Analyze diff content semantically.

        Args:
            diff_files: List of changed file paths
            changed_content: Raw diff content or file contents
            mr_title: MR title for context

        Returns:
            ToolResult with semantic analysis dict
        """
        if not settings.ai_enabled or not settings.ai_api_key:
            # Fallback: basic analysis without LLM
            return ToolResult.ok(self._fallback_analysis(diff_files, mr_title))

        try:
            import httpx

            user_prompt = f"MR Title: {mr_title}\n\nChanged files:\n"
            if diff_files:
                user_prompt += "\n".join(f"  - {f}" for f in diff_files)
            if changed_content:
                user_prompt += f"\n\nContent:\n{changed_content[:3000]}"

            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{settings.ai_api_base}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.ai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.ai_model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.2,
                        "max_tokens": 1024,
                        "response_format": {"type": "json_object"},
                    },
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]

            result = json.loads(content.strip())
            logger.info(
                "Diff analysis: %d interfaces, risk=%s",
                len(result.get("interfaces_changed", [])),
                result.get("risk_level", "unknown"),
            )
            return ToolResult.ok(result)

        except Exception as e:
            logger.warning("Diff analysis failed, using fallback: %s", e)
            return ToolResult.ok(self._fallback_analysis(diff_files, mr_title))

    def _fallback_analysis(self, diff_files: Optional[list[str]], mr_title: str) -> dict:
        """Rule-based fallback when LLM is unavailable."""
        files = diff_files or []
        return {
            "summary": f"MR: {mr_title}. Changes in {len(files)} file(s).",
            "interfaces_changed": [],
            "modules_affected": list(set(
                f.split("/")[0] if "/" in f else "root" for f in files
            )),
            "risk_level": "low",
            "risk_items": [],
            "security_concerns": [],
        }
