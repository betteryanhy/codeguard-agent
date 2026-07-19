"""LLM-driven planner: analyzes events and produces execution plans."""

import json
import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# System prompt for the planner LLM
# ------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """You are the planning module of PR-CodeGuard Agent, a code review agent.
Your job is to analyze incoming events and produce a structured execution plan.

Available tools:
- get_diff: Fetch the MR diff/changes from GitLab (params: mr_id)
- run_scanners: Run code scan engines on the repository (params: task_id, repo_url, mr_id, source_branch, target_branch, diff_files)
- semantic_analyze: Analyze diff content semantically using LLM (params: diff_files, changed_content)
- check_knowledge: Search the knowledge base for relevant context (params: query)
- write_knowledge: Write project baseline or MR record to knowledge base (params: record_type, data)
- write_comment: Post a review comment to the MR (params: repo_url, mr_id, body)

Event types and how to handle them:

1. MR_EVENT - Merge Request opened/reopened/updated
   Plan: get_diff -> semantic_analyze -> check_knowledge -> run_scanners -> write_knowledge -> write_comment

2. QUESTION - Natural language question from user
   Plan: check_knowledge -> (answer based on knowledge)

3. BUILD_BASELINE - Build initial project understanding
   Plan: run_scanners -> semantic_analyze -> write_knowledge

Always respond with a JSON object containing:
{
  "thought": "brief analysis of the event",
  "plan": [
    {"step": 1, "tool": "tool_name", "params": {"param1": "value1", ...}},
    ...
  ]
}

Do NOT include any text outside the JSON object.
"""


class Planner:
    """Generates execution plans using LLM or rule-based fallback."""

    def __init__(self):
        self._api_base = settings.ai_api_base.rstrip("/")
        self._api_key = settings.ai_api_key
        self._model = settings.ai_model

    async def plan(self, event_type: str, context: dict[str, Any]) -> list[dict]:
        """Generate an execution plan for the given event.

        Args:
            event_type: Type of event (MR_EVENT, QUESTION, BUILD_BASELINE)
            context: Event-specific data

        Returns:
            List of tool call dicts: [{"tool": "name", "params": {...}}, ...]
        """
        if not settings.ai_enabled or not self._api_key:
            return self._fallback_plan(event_type, context)

        return await self._llm_plan(event_type, context)

    def _fallback_plan(self, event_type: str, context: dict) -> list[dict]:
        """Rule-based fallback when AI is not available."""
        logger.info("AI disabled, using fallback plan for %s", event_type)

        if event_type == "MR_EVENT":
            return [
                {"tool": "run_scanners", "params": {
                    "task_id": context.get("task_id", ""),
                    "repo_url": context.get("repo_url", ""),
                    "mr_id": context.get("mr_id", 0),
                    "source_branch": context.get("source_branch", ""),
                    "target_branch": context.get("target_branch", ""),
                    "diff_files": context.get("diff_files"),
                }},
            ]
        elif event_type == "BUILD_BASELINE":
            return [
                {"tool": "run_scanners", "params": context},
            ]
        elif event_type == "QUESTION":
            return [
                {"tool": "check_knowledge", "params": {"query": context.get("question", "")}},
            ]
        return []

    async def _llm_plan(self, event_type: str, context: dict) -> list[dict]:
        """Use LLM to generate an execution plan."""
        user_prompt = f"Event type: {event_type}\nContext: {json.dumps(context, ensure_ascii=False)}"

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._api_base}/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [
                            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 1024,
                    },
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]

            # Parse JSON response
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("\n", 1)[0]
            result = json.loads(content)
            return result.get("plan", [])

        except Exception as e:
            logger.warning("LLM planning failed, using fallback: %s", e)
            return self._fallback_plan(event_type, context)
