"""Agent Brain: main decision loop for event processing.

Entry point for all events (webhook, questions, etc).
Analyzes context → generates plan → executes tools → returns results.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional

from app.config import settings
from app.agent.planner import Planner
from app.agent.executor import ToolExecutor

logger = logging.getLogger(__name__)


class AgentBrain:
    """Central decision-making loop for the PR-CodeGuard Agent."""

    def __init__(self, strategy_mgr: object = None):
        self.planner = Planner()
        self.executor = ToolExecutor(strategy_mgr=strategy_mgr)

    async def process_mr_event(
        self,
        task_id: str,
        repo_url: str,
        mr_id: int,
        source_branch: str,
        target_branch: str,
        mr_title: str = "",
        diff_files: list[str] | None = None,
        author: str = "",
        should_scan: bool = True,
    ) -> dict[str, Any]:
        """Process a Merge Request event (open/reopen/update/merge).

        For open/reopen/update: scans code, records findings, commits, and knowledge.
        For merge: records merge info and commits without re-scanning.

        Returns:
            Dict with execution results and final output.
        """
        logger.info(
            "AgentBrain processing MR event: %s MR !%d (%s → %s) action=%s author=%s",
            repo_url, mr_id, source_branch, target_branch,
            "scan" if should_scan else "merge", author,
        )

        findings = []
        plan = []

        # --- Phase 1: Scan code (only for open/reopen/update) ---
        if should_scan:
            context = {
                "task_id": task_id,
                "repo_url": repo_url,
                "mr_id": mr_id,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "mr_title": mr_title,
                "diff_files": diff_files,
            }
            plan = await self.planner.plan("MR_EVENT", context)
            if plan:
                results = await self.executor.execute_plan(plan)
                scan_result = results.get("run_scanners")
                scan_task = scan_result.data if scan_result and scan_result.success else None
                findings = scan_task.findings if scan_task else []
            else:
                logger.warning("Empty plan for MR event")

            # --- Phase 1b: Terraform change risk analysis ---
            try:
                from app.services.gitlab_client import GitLabClient
                from app.engine.tf_change_analyzer import TfChangeAnalyzer

                client = GitLabClient()
                raw_diffs = client.get_mr_raw_diffs(repo_url, mr_id)
                if raw_diffs:
                    analyzer = TfChangeAnalyzer()
                    tf_findings = analyzer.analyze(raw_diffs)
                    if tf_findings:
                        findings.extend(tf_findings)
                        logger.info(
                            "TF change analysis: %d findings (critical=%d, major=%d)",
                            len(tf_findings),
                            sum(1 for f in tf_findings if f.severity in ("critical", "blocker")),
                            sum(1 for f in tf_findings if f.severity == "major"),
                        )
            except Exception as e:
                logger.warning("TF change analysis failed: %s", e)
        else:
            logger.info("Skipping scan (merge event)")

        # --- Phase 2: Record knowledge (commits, diff stats, MR info) ---
        if settings.knowledge_enabled:
            await self._record_full_mr_knowledge(
                repo_url=repo_url,
                mr_id=mr_id,
                mr_title=mr_title,
                source_branch=source_branch,
                target_branch=target_branch,
                author=author,
                findings=findings,
                is_merge=not should_scan,  # merge event when not scanning
            )

        # --- Phase 3: Build and post comment (only for scan events) ---
        if should_scan:
            comment = await self._build_comment(findings, repo_url=repo_url)
            if comment and settings.knowledge_enabled:
                comment_result = await self.executor.execute_step({
                    "tool": "write_comment",
                    "params": {
                        "repo_url": repo_url,
                        "mr_id": mr_id,
                        "body": comment,
                    },
                })
                if hasattr(self.executor, '_last_results'):
                    pass  # results tracking

        # --- Phase 4: Send alerts if critical findings found ---
        if should_scan and settings.alert_enabled and findings:
            try:
                from app.services.alert_service import AlertService
                alert = AlertService()
                alert.notify(
                    findings=findings,
                    repo_url=repo_url,
                    mr_id=mr_id,
                    mr_title=mr_title,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    author=author,
                )
            except Exception as e:
                logger.warning("Failed to send alert: %s", e)

        return {
            "status": "completed",
            "findings_count": len(findings),
            "findings": findings,
            "plan": plan,
        }

    async def process_question(self, question: str, repo_url: str = "") -> dict[str, Any]:
        """Process a natural language question from a user."""
        context = {"question": question, "repo_url": repo_url}
        plan = await self.planner.plan("QUESTION", context)
        results = await self.executor.execute_plan(plan)
        return {"status": "completed", "plan": plan, "tool_results": {k: str(v) for k, v in results.items()}}

    async def build_baseline(self, repo_url: str, branch: str = "master") -> dict[str, Any]:
        """Build initial project baseline understanding."""
        context = {"repo_url": repo_url, "source_branch": branch}
        plan = await self.planner.plan("BUILD_BASELINE", context)
        results = await self.executor.execute_plan(plan)
        return {"status": "completed", "plan": plan, "tool_results": {k: str(v) for k, v in results.items()}}

    # ------------------------------------------------------------------
    # Knowledge recording (commits + diff stats + MR record)
    # ------------------------------------------------------------------

    async def _record_full_mr_knowledge(
        self,
        repo_url: str,
        mr_id: int,
        mr_title: str,
        source_branch: str,
        target_branch: str,
        author: str = "",
        findings: list | None = None,
        is_merge: bool = False,
    ):
        """Record MR, commits, and file changes to knowledge base.

        Args:
            is_merge: True for merge events, False for open/update events.
        """
        try:
            from app.main import knowledge_base
            if not knowledge_base:
                return

            findings = findings or []

            # 1. Fetch commits and diff stats from GitLab
            commits_data = []
            diff_stats = []
            try:
                from app.services.gitlab_client import GitLabClient
                client = GitLabClient()
                commits_data = client.get_mr_commits(repo_url, mr_id)
                diff_stats = client.get_mr_diff_stats(repo_url, mr_id)
                logger.info(
                    "Fetched %d commits and %d file changes for MR !%d",
                    len(commits_data), len(diff_stats), mr_id,
                )
            except Exception as e:
                logger.warning("Failed to fetch MR commits/stats: %s", e)

            # 2. Save individual commit records
            total_additions = 0
            total_deletions = 0
            commit_authors = set()

            from app.knowledge.schemas import CommitRecord, MrRecord

            for cd in commits_data:
                stats = cd.get("stats", {}) or {}
                rec = CommitRecord(
                    mr_id=mr_id,
                    repo_url=repo_url,
                    commit_id=cd.get("id", ""),
                    short_id=cd.get("short_id", ""),
                    title=cd.get("title", ""),
                    author_name=cd.get("author_name", ""),
                    author_email=cd.get("author_email", ""),
                    committed_date=self._parse_gitlab_date(cd.get("committed_date")),
                    additions=stats.get("additions", 0),
                    deletions=stats.get("deletions", 0),
                    total_changes=stats.get("total", 0),
                    files_changed=stats.get("total", 0) if "total" in stats else 0,
                )
                knowledge_base.save_commit_record(rec)
                total_additions += rec.additions
                total_deletions += rec.deletions
                if rec.author_name:
                    commit_authors.add(rec.author_name)

            # 3. Save individual file change records
            from app.knowledge.schemas import FileChange
            for ds in diff_stats:
                fc = FileChange(
                    mr_id=mr_id,
                    repo_url=repo_url,
                    file_path=ds.get("file_path", ""),
                    old_path=ds.get("old_path", ""),
                    new_file=ds.get("new_file", False),
                    renamed_file=ds.get("renamed_file", False),
                    deleted_file=ds.get("deleted_file", False),
                    additions=ds.get("additions", 0),
                    deletions=ds.get("deletions", 0),
                )
                knowledge_base.save_file_change(fc)

            # 4. Save / update MR record with full info
            summary = f"MR !{mr_id}: {mr_title}"
            if findings:
                summary += f" ({len(findings)} issues found)"
            summary += f" | +{total_additions} -{total_deletions} lines | {len(commits_data)} commits"

            risks_json = json.dumps([
                {"severity": f.severity, "message": f.message, "file": f.file_path}
                for f in (findings or [])
            ])

            # Set merged_at only for actual merge events
            merged_at = datetime.utcnow() if is_merge else None
            commit_author_str = author or ", ".join(sorted(commit_authors))

            existing = knowledge_base.get_mr_record(repo_url, mr_id)
            if existing:
                # Update existing record in-place
                knowledge_base.update_mr_record(
                    repo_url=repo_url,
                    mr_id=mr_id,
                    mr_title=mr_title,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    author=commit_author_str,
                    merged_at=merged_at,
                    summary=summary,
                    risks=risks_json,
                )
            else:
                record = MrRecord(
                    repo_url=repo_url,
                    mr_id=mr_id,
                    mr_title=mr_title,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    author=commit_author_str,
                    merged_at=merged_at,
                    summary=summary,
                    risks=risks_json,
                )
                knowledge_base.save_mr_record(record)

            logger.info(
                "MR knowledge recorded for !%d (author=%s, +%d/-%d, %d commits, %d file changes)",
                mr_id, author or ", ".join(sorted(commit_authors)),
                total_additions, total_deletions,
                len(commits_data), len(diff_stats),
            )

            # 5. Add semantic to Chroma
            chroma_doc = (
                f"MR !{mr_id}: {mr_title}. "
                f"Branch: {source_branch} → {target_branch}. "
                f"Author: {author or ', '.join(sorted(commit_authors))}. "
                f"Changes: +{total_additions} -{total_deletions} lines in {len(commits_data)} commits. "
                f"{summary}"
            )
            repo_name = repo_url.split("/")[-1].replace(".git", "")
            knowledge_base.add_mr_semantic(
                mr_id_str=f"mr::{repo_name}::{mr_id}",
                document=chroma_doc,
                metadata={
                    "repo_url": repo_url,
                    "mr_id": mr_id,
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "author": author or ", ".join(sorted(commit_authors)),
                    "total_additions": total_additions,
                    "total_deletions": total_deletions,
                    "total_commits": len(commits_data),
                },
            )

        except Exception as e:
            logger.warning("Failed to record full MR knowledge: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # Comment building
    # ------------------------------------------------------------------

    async def _build_comment(self, findings, repo_url: str = "") -> str | None:
        """Build a review comment from findings, enriched with knowledge context."""
        from app.services.comment_builder import CommentBuilder
        builder = CommentBuilder()

        context_lines = []
        if settings.knowledge_enabled and repo_url:
            try:
                from app.main import knowledge_base
                if knowledge_base:
                    recent_mrs = knowledge_base.get_mr_records(repo_url, limit=3)
                    if recent_mrs:
                        context_lines.append("\n> **相关历史 MR：**")
                        for rec in recent_mrs:
                            context_lines.append(f"> - !{rec.mr_id} {rec.mr_title} ({rec.author or 'unknown'})")
            except Exception as e:
                logger.debug("Failed to enrich comment with context: %s", e)

        comment = builder.build_review(findings)
        if context_lines:
            comment += "\n" + "\n".join(context_lines)

        return comment

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_gitlab_date(date_str: str | None) -> Optional[datetime]:
        """Parse GitLab ISO 8601 date string to datetime."""
        if not date_str:
            return None
        try:
            if "T" in date_str:
                # Handle timezone like +08:00 or Z
                if date_str.endswith("Z"):
                    date_str = date_str[:-1]
                elif "+" in date_str[19:] or "-" in date_str[19:]:
                    date_str = date_str[:19]
                return datetime.fromisoformat(date_str)
            return datetime.strptime(date_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
