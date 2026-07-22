"""Natural language query engine for code activity Q&A.

Combines keyword extraction and vector search to answer questions about
code changes, developer activity, and project history.

Query types supported:
  - "user_service.go 这个文件最近谁改过？" → Find file changes by path
  - "payment 模块上周有什么变更？" → Semantic search for module activity
  - "张三最近提交了什么？" → Search by author name
  - "昨天有什么高风险MR？" → Search by date range + risk keywords
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from app.knowledge.knowledge_base import KnowledgeBase
from app.knowledge.schemas import CommitRecord, MrRecord

logger = logging.getLogger(__name__)

# Chinese and English stop words
STOP_WORDS = {
    "的", "了", "在", "是", "谁", "什么", "最近", "上周", "这个",
    "有", "过", "吗", "吧", "啊", "呢", "哪", "怎么", "如何", "哪些",
    "the", "a", "an", "is", "was", "were", "has", "have", "been",
    "do", "does", "did", "to", "in", "for", "on", "at", "by",
    "with", "from", "of", "and", "or", "but", "not",
}

# File extension patterns for detecting file name mentions
FILE_EXT_PATTERN = re.compile(r"\b\w+\.\w{1,5}\b")


class QueryEngine:
    """Unified query engine combining keyword matching and vector search."""

    def __init__(self, kb: KnowledgeBase | None = None):
        self.kb = kb or KnowledgeBase()

    async def query(self, question: str) -> dict:
        """Answer a natural language question about code activity.

        Args:
            question: Natural language question (Chinese or English).

        Returns:
            dict with "answer", "source_count", and "sources" fields.
        """
        question = question.strip()
        if not question:
            return {
                "question": question,
                "answer": "请提供具体的问题。例如：\"user_service.go 最近谁改过？\"",
                "source_count": 0,
                "sources": [],
            }

        # 1. Extract keywords and intent
        keywords = self._extract_keywords(question)
        intent = self._detect_intent(question, keywords)

        # 2. Try vector search first (semantic)
        vector_results = []
        try:
            vector_results = self.kb.search_mr(question, n_results=5)
        except Exception as e:
            logger.debug("Vector search failed: %s", e)

        # 3. Try keyword-based search
        keyword_results = self._keyword_search(keywords, intent)

        # 4. Merge results
        merged = self._merge_results(vector_results, keyword_results)

        # 5. Format answer
        answer = self._format_answer(merged, question, intent, keywords)

        return {
            "question": question,
            "answer": answer,
            "source_count": len(merged),
            "sources": merged[:5],
        }

    # ------------------------------------------------------------------
    # Intent detection
    # ------------------------------------------------------------------

    def _detect_intent(self, question: str, keywords: list[str]) -> str:
        """Detect the user's query intent."""
        q = question.lower()

        # File-specific query (highest priority - specific match)
        if any(kw for kw in keywords if "." in kw):
            return "file"

        # Risk/security query (check before time to avoid "最近有风险" matching time)
        if any(kw in q for kw in ("风险", "安全", "漏洞", "高危", "risk", "security", "vuln")):
            return "risk"

        # Date/time query
        if any(kw in q for kw in ("昨天", "今天", "上周", "最近", "前天", "yesterday", "today", "week")):
            return "time"

        # People/author query
        if any(kw in q for kw in ("谁", "改过", "提交", "author", "committer")):
            return "author"

        # General MR query
        if any(kw in q for kw in ("mr", "merge", "合并", "pr", "pull request")):
            return "mr"

        # Module/component query
        if any(kw in q for kw in ("模块", "组件", "项目", "module", "component", "project")):
            return "module"

        return "general"

    # ------------------------------------------------------------------
    # Keyword extraction
    # ------------------------------------------------------------------

    def _extract_keywords(self, question: str) -> list[str]:
        """Extract meaningful keywords from a natural language question."""
        words = question.lower().split()
        keywords = [
            w.strip("？?，,。.!！：:""''（）()【】[]《》<>")
            for w in words
            if w not in STOP_WORDS and len(w) > 1
        ]

        # Detect file paths (words containing file extensions)
        file_keywords = [k for k in keywords if FILE_EXT_PATTERN.match(k)]
        return file_keywords or keywords

    # ------------------------------------------------------------------
    # Keyword search
    # ------------------------------------------------------------------

    def _keyword_search(self, keywords: list[str], intent: str) -> list[dict]:
        """Search knowledge base using keyword matching."""
        results = []
        seen = set()

        if not keywords:
            return results

        # Search by author
        if intent == "author":
            for kw in keywords:
                name = kw.strip("?？ ")
                try:
                    commits = self.kb.get_commits_by_author("", name)
                    for c in commits:
                        key = f"commit_{c.commit_id}"
                        if key not in seen:
                            seen.add(key)
                            results.append(self._commit_to_dict(c))
                except Exception:
                    pass

        # Search commits by keywords in title
        try:
            all_commits = self.kb.get_all_commits_by_date_range(
                datetime.utcnow() - timedelta(days=90),
                datetime.utcnow(),
            )
            for c in all_commits:
                title_lower = c.title.lower()
                if any(kw in title_lower for kw in keywords):
                    key = f"commit_{c.commit_id}"
                    if key not in seen:
                        seen.add(key)
                        results.append(self._commit_to_dict(c))
        except Exception as e:
            logger.debug("Keyword commit search failed: %s", e)

        # Search MR records by keywords
        try:
            from app.services.storage import StorageService
            storage = StorageService()
            all_mrs = storage.get_all_tasks()
            for task in (all_mrs or []):
                task_title = (getattr(task, "mr_title", "") or "")
                repo = (getattr(task, "repo_url", "") or "")
                if any(kw in task_title.lower() for kw in keywords) or any(kw in repo.lower() for kw in keywords):
                    key = f"mr_{task.mr_id}"
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "type": "mr",
                            "mr_id": task.mr_id,
                            "title": task_title,
                            "repo_url": repo,
                            "status": getattr(task, "status", ""),
                            "created_at": str(getattr(task, "created_at", "") or ""),
                        })
        except Exception as e:
            logger.debug("MR keyword search failed: %s", e)

        return results

    # ------------------------------------------------------------------
    # Result merging
    # ------------------------------------------------------------------

    def _merge_results(self, vector_results: list[dict], keyword_results: list[dict]) -> list[dict]:
        """Merge vector and keyword results, deduplicating by key."""
        seen_keys = set()
        merged = []

        # Vector results first (higher relevance)
        for r in vector_results:
            key = r.get("id", "") or r.get("mr_id", "")
            if not key:
                key = str(hash(str(r)))
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(r)

        # Then keyword results
        for r in keyword_results:
            key = r.get("id", "") or r.get("mr_id", "")
            if not key:
                key = str(hash(str(r)))
            if key not in seen_keys:
                seen_keys.add(key)
                merged.append(r)

        return merged[:10]

    # ------------------------------------------------------------------
    # Answer formatting
    # ------------------------------------------------------------------

    def _format_answer(
        self,
        sources: list[dict],
        question: str,
        intent: str,
        keywords: list[str],
    ) -> str:
        """Format query results into a human-readable answer."""
        if not sources:
            return self._no_results_answer(question)

        lines = []
        file_keywords = [k for k in keywords if "." in k]

        # File-specific context
        if file_keywords:
            target_file = file_keywords[0]
            file_sources = [
                s for s in sources
                if s.get("type") == "commit" and target_file in s.get("file_path", "").lower()
            ]
            if file_sources:
                s = file_sources[0]
                lines.append(
                    f"文件 `{target_file}` 最近由 **{s.get('author_name', '未知')}** "
                    f"修改 (commit: {s.get('short_id', '')})"
                )
            else:
                lines.append(f"未找到文件 `{target_file}` 的修改记录")

        # Author-specific
        elif intent == "author" and sources:
            by_author = [s for s in sources if s.get("type") == "commit"]
            if by_author:
                author = by_author[0].get("author_name", keywords[0] if keywords else "未知")
                lines.append(f"**{author}** 最近的提交活动：")
                for s in by_author[:5]:
                    lines.append(
                        f"  - `{s.get('short_id', '')}` {s.get('title', '')} "
                        f"({s.get('committed_date', '')})"
                    )

        # Time-based
        elif intent == "time" and sources:
            lines.append(f"找到 {len(sources)} 条相关记录：")
            for s in sources[:5]:
                stype = s.get("type", "记录")
                title = s.get("title") or s.get("message", "")
                date = s.get("committed_date") or s.get("created_at", "")
                lines.append(f"  - [{stype}] {title} ({date})")

        # MR-focused
        elif intent == "mr" and sources:
            lines.append(f"找到 {len(sources)} 个相关 MR：")
            for s in sources[:5]:
                lines.append(
                    f"  - !{s.get('mr_id', '?')} {s.get('title', '')} "
                    f"({s.get('author', s.get('author_name', ''))})"
                )

        # General: summarize what was found
        else:
            commit_count = sum(1 for s in sources if s.get("type") == "commit")
            mr_count = sum(1 for s in sources if s.get("type") == "mr")
            parts = []
            if commit_count:
                parts.append(f"{commit_count} 次提交")
            if mr_count:
                parts.append(f"{mr_count} 个 MR")
            if parts:
                lines.append(f"找到 {'、'.join(parts)}：")
                for s in sources[:5]:
                    title = s.get("title") or s.get("message", "")
                    if title:
                        lines.append(f"  - {title}")
            else:
                lines.append(f"找到 {len(sources)} 条相关记录")

        lines.append("")
        lines.append(f"*共查找到 {len(sources)} 条相关记录*")
        return "\n".join(lines)

    def _no_results_answer(self, question: str) -> str:
        """Generate a helpful response when no results are found."""
        return (
            f"未找到与 \"{question}\" 相关的记录。可能的原因：\n"
            f"  1. 该事件尚未被记录到知识库\n"
            f"  2. GitLab webhook 配置尚未推送该类型事件\n"
            f"  3. 尝试换个关键词或使用更具体的文件名查询"
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _commit_to_dict(c: CommitRecord) -> dict:
        """Convert a CommitRecord to a dictionary."""
        return {
            "type": "commit",
            "commit_id": c.commit_id,
            "short_id": c.short_id,
            "title": c.title,
            "author_name": c.author_name,
            "author_email": c.author_email,
            "committed_date": str(c.committed_date) if c.committed_date else "",
            "additions": c.additions,
            "deletions": c.deletions,
            "file_path": c.title,  # Use title as a rough file indicator
        }
