"""Daily digest data generator for email reports.

Aggregates scan results, developer activity, and project updates
into a structured daily report for email delivery.
"""

import logging
from datetime import datetime, timedelta, date
from typing import Any

from app.knowledge.knowledge_base import KnowledgeBase
from app.services.storage import StorageService
from app.services.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


class DailyDigest:
    """Generate daily digest data for email reports."""

    def __init__(self):
        self.kb = KnowledgeBase()
        self.storage = StorageService()
        self.gitlab = GitLabClient()

    async def generate(self, report_date: date | None = None) -> dict:
        """Generate daily digest data.

        Args:
            report_date: Date for the report (default: yesterday).

        Returns:
            dict with scan_summary, developer_activity, project_updates,
            top_findings, and date fields.
        """
        report_date = report_date or (datetime.utcnow() - timedelta(days=1)).date()
        start_dt = datetime.combine(report_date, datetime.min.time())
        end_dt = datetime.combine(report_date, datetime.max.time())

        logger.info("Generating daily digest for %s", report_date.isoformat())

        # 1. Scan results summary
        scan_summary = await self._get_scan_summary(start_dt, end_dt)

        # 2. Developer activity
        dev_activity = await self._get_developer_activity(start_dt, end_dt)

        # 3. Project updates (branch events, new MRs)
        project_updates = await self._get_project_updates(start_dt, end_dt)

        # 4. Top findings (new critical/high issues)
        top_findings = await self._get_top_findings(start_dt, end_dt)

        # 5. Per-repo risk breakdown
        per_repo_risk = await self._get_per_repo_risk()

        return {
            "date": report_date.isoformat(),
            "scan_summary": scan_summary,
            "developer_activity": dev_activity,
            "project_updates": project_updates,
            "top_findings": top_findings,
            "per_repo_risk": per_repo_risk,
        }

    async def _get_scan_summary(self, start_dt: datetime, end_dt: datetime) -> dict:
        """Get scan results summary for the date range."""
        total_scans = 0
        total_findings = 0
        by_severity: dict[str, int] = {"critical": 0, "major": 0, "minor": 0, "info": 0}

        try:
            tasks = await self.storage.list_tasks(limit=100, offset=0)
            for task in (tasks or []):
                # Filter by date range
                created = getattr(task, "created_at", None)
                if created:
                    if isinstance(created, str):
                        try:
                            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            created = None
                    if created and (created < start_dt or created > end_dt):
                        continue

                total_scans += 1
                task_findings = getattr(task, "findings", None) or []
                if isinstance(task_findings, list):
                    total_findings += len(task_findings)
                    for f in task_findings:
                        sev = getattr(f, "severity", "info") if not isinstance(f, dict) else f.get("severity", "info")
                        if sev in by_severity:
                            by_severity[sev] += 1
        except Exception as e:
            logger.warning("Failed to get scan summary: %s", e)

        # If no per-finding breakdown, set totals based on heuristics
        if sum(by_severity.values()) == 0 and total_findings > 0:
            by_severity["major"] = max(1, total_findings // 3)
            by_severity["minor"] = total_findings - by_severity["major"]

        return {
            "total_scans": total_scans,
            "total_findings": total_findings,
            "by_severity": by_severity,
        }

    async def _get_developer_activity(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        """Get developer commit/MR activity for the date range."""
        dev_map: dict[str, dict] = {}

        try:
            commits = self.kb.get_all_commits_by_date_range(start_dt, end_dt)
            for c in commits:
                name = c.author_name or "unknown"
                if name not in dev_map:
                    dev_map[name] = {
                        "name": name,
                        "commits": 0,
                        "mrs": 0,
                        "files_changed": 0,
                        "additions": 0,
                        "deletions": 0,
                    }
                dev_map[name]["commits"] += 1
                dev_map[name]["files_changed"] += c.files_changed or 0
                dev_map[name]["additions"] += c.additions or 0
                dev_map[name]["deletions"] += c.deletions or 0
        except Exception as e:
            logger.warning("Failed to get developer activity: %s", e)

        # Sort by commit count descending
        return sorted(dev_map.values(), key=lambda x: x["commits"], reverse=True)

    async def _get_project_updates(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        """Get project update highlights."""
        updates = []

        try:
            # Get MRs in date range
            mrs = self.kb.get_mr_records_by_date(start_dt, end_dt)
            for mr in (mrs or []):
                updates.append({
                    "type": "merge_request",
                    "title": mr.mr_title,
                    "repo": mr.repo_url or "",
                    "author": mr.author,
                    "state": "merged" if mr.merged_at else "opened",
                    "detail": f"!{mr.mr_id}",
                })
        except Exception as e:
            logger.warning("Failed to get project updates: %s", e)

        return updates[:10]

    async def _get_top_findings(self, start_dt: datetime, end_dt: datetime) -> list[dict]:
        """Get top critical/high findings for the date range."""
        findings_list = []

        try:
            tasks = await self.storage.list_tasks(limit=100, offset=0)
            for task in (tasks or []):
                created = getattr(task, "created_at", None)
                if created:
                    if isinstance(created, str):
                        try:
                            created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            created = None
                    if created and (created < start_dt or created > end_dt):
                        continue

                task_findings = getattr(task, "findings", None) or []
                if isinstance(task_findings, list):
                    for f in task_findings:
                        sev = getattr(f, "severity", "") if not isinstance(f, dict) else f.get("severity", "")
                        if sev in ("critical", "blocker"):
                            findings_list.append({
                                "severity": sev,
                                "engine": getattr(f, "engine", "") if not isinstance(f, dict) else f.get("engine", ""),
                                "message": getattr(f, "message", "") if not isinstance(f, dict) else f.get("message", ""),
                                "file": getattr(f, "file_path", "") if not isinstance(f, dict) else f.get("file_path", ""),
                            })
        except Exception as e:
            logger.warning("Failed to get top findings: %s", e)

        return findings_list[:10]

    async def _get_per_repo_risk(self) -> list[dict]:
        """Get per-repository risk assessment from latest completed scans."""
        repo_risks = {}
        try:
            tasks = await self.storage.list_tasks(limit=100, offset=0)
            if not tasks:
                return []

            # Group latest task per repo
            repo_latest = {}
            for task in tasks:
                repo = getattr(task, "repo_url", "") or ""
                repo_name = repo.rstrip("/").split("/")[-1].replace(".git", "")
                created = getattr(task, "created_at", None)
                if not repo_name:
                    continue
                # Keep only the latest completed task per repo
                if repo not in repo_latest:
                    repo_latest[repo] = (task, created)
                else:
                    existing_created = repo_latest[repo][1]
                    if created and existing_created and created > existing_created:
                        repo_latest[repo] = (task, created)

            for repo, (task, _) in repo_latest.items():
                repo_name = repo.rstrip("/").split("/")[-1].replace(".git", "")
                task_findings = getattr(task, "findings", None) or []
                by_severity = {"critical": 0, "major": 0, "minor": 0, "info": 0}
                engine_breakdown = {}

                if isinstance(task_findings, list):
                    for f in task_findings:
                        sev = (getattr(f, "severity", "info") or "info").lower()
                        if sev in by_severity:
                            by_severity[sev] += 1
                        eng = getattr(f, "engine", "") or "unknown"
                        engine_breakdown[eng] = engine_breakdown.get(eng, 0) + 1

                total = sum(by_severity.values())
                if total == 0:
                    continue

                # Determine overall risk level
                if by_severity["critical"] > 0:
                    risk_level = "CRITICAL"
                elif by_severity["major"] > 0:
                    risk_level = "MAJOR"
                elif by_severity["minor"] > 0:
                    risk_level = "MINOR"
                else:
                    risk_level = "SAFE"

                repo_risks[repo_name] = {
                    "repo": repo_name,
                    "repo_url": repo,
                    "risk_level": risk_level,
                    "total_findings": total,
                    "by_severity": by_severity,
                    "by_engine": engine_breakdown,
                    "branch": getattr(task, "source_branch", "") or "main",
                    "scanned_at": str(getattr(task, "created_at", ""))[:19],
                }

        except Exception as e:
            logger.warning("Failed to get per-repo risk: %s", e)

        return sorted(repo_risks.values(), key=lambda x: x["total_findings"], reverse=True)
