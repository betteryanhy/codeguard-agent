"""Tool for reading and searching the knowledge base."""

import logging
from typing import Optional

from app.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class KnowledgeReaderTool(BaseTool):
    """Search and retrieve information from the knowledge base."""

    @property
    def name(self) -> str:
        return "check_knowledge"

    async def execute(
        self,
        query: str = "",
        repo_url: str = "",
        search_type: str = "auto",
        n_results: int = 5,
        **kwargs,
    ) -> ToolResult:
        """Search the knowledge base.

        Args:
            query: Natural language query or keyword
            repo_url: Optional filter by repository
            search_type: "code", "mr", "auto" (auto-detect)
            n_results: Number of results to return

        Returns:
            ToolResult with formatted knowledge text
        """
        from app.main import knowledge_base
        if not knowledge_base:
            return ToolResult.fail("Knowledge base not initialized")

        try:
            results = []

            # Determine search type
            if search_type == "auto":
                # Try semantic search on both collections
                try:
                    code_results = knowledge_base.search_code(query, n_results)
                    mr_results = knowledge_base.search_mr(query, n_results)
                    results = (code_results or []) + (mr_results or [])
                except Exception:
                    pass

                # Also search MR records if repo_url is given
                if repo_url:
                    mr_records = knowledge_base.get_mr_records(repo_url, n_results)
                    for rec in mr_records:
                        results.append({
                            "type": "mr_record",
                            "mr_id": rec.mr_id,
                            "title": rec.mr_title,
                            "summary": rec.summary,
                            "author": rec.author,
                        })
            elif search_type == "code":
                results = knowledge_base.search_code(query, n_results)
            elif search_type == "mr":
                results = knowledge_base.search_mr(query, n_results)
                if repo_url:
                    mr_records = knowledge_base.get_mr_records(repo_url, n_results)
                    for rec in mr_records:
                        results.append({
                            "type": "mr_record",
                            "mr_id": rec.mr_id,
                            "title": rec.mr_title,
                            "summary": rec.summary,
                        })

            # Format results as readable text
            if not results:
                return ToolResult.ok({"answer": "No relevant knowledge found.", "results": []})

            formatted = self._format_results(results, query)
            return ToolResult.ok({"answer": formatted, "results": results})

        except Exception as e:
            logger.error("Knowledge search failed: %s", e)
            return ToolResult.fail(str(e))

    def _format_results(self, results: list[dict], query: str) -> str:
        """Format search results into readable text."""
        lines = [f"基于知识库的查询: '{query}'", ""]

        for i, r in enumerate(results[:5], 1):
            rtype = r.get("type", r.get("metadata", {}).get("type", "unknown"))

            if rtype == "mr_record":
                lines.append(f"{i}. MR !{r.get('mr_id', '?')}: {r.get('title', '')}")
                if r.get("summary"):
                    lines.append(f"   摘要: {r['summary']}")
                if r.get("author"):
                    lines.append(f"   作者: {r['author']}")

            elif rtype in ("file", "code_chunk"):
                meta = r.get("metadata", {})
                fp = meta.get("file_path", "")
                lines.append(f"{i}. 文件: {fp}")
                if r.get("document"):
                    lines.append(f"   说明: {r['document'][:200]}")

            else:
                lines.append(f"{i}. {r.get('document', json.dumps(r, ensure_ascii=False)[:200])}")

        return "\n".join(lines)
