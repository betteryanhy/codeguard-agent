"""Daily report API - aggregate developer productivity and project changes."""

import logging
from datetime import datetime, date, timedelta
from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


@router.get("/daily")
async def daily_report(
    date_str: str = Query(default="", description="Date in YYYY-MM-DD format"),
    repo_url: str = Query(default="", description="Filter by repository URL"),
):
    """Generate a daily productivity report.

    Aggregates:
    - MRs merged on this date
    - Commits per developer (additions, deletions, files changed)
    - File-level change summary
    - Security findings discovered

    Args:
        date_str: Date string (YYYY-MM-DD). Defaults to today.
        repo_url: Optional repo URL filter.

    Returns:
        Structured daily report with per-developer and per-repo stats.
    """
    from app.main import knowledge_base
    if not knowledge_base:
        return {"error": "Knowledge base not initialized"}

    # Parse date range
    if date_str:
        try:
            report_date = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return {"error": f"Invalid date format: {date_str}. Use YYYY-MM-DD"}
    else:
        report_date = datetime.utcnow()

    day_start = report_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    # Get MR records created on this date (covers both open and merge events)
    try:
        mr_records = knowledge_base.sqlite.get_mr_records_by_date(day_start, day_end, repo_url)
    except AttributeError:
        # Fallback: use get_mr_records and filter by created_at
        if repo_url:
            all_records = knowledge_base.get_mr_records(repo_url, limit=200)
        else:
            all_records = []
            logger.warning("Date-range filtering not available without repo_url")
        mr_records = [
            r for r in all_records
            if r.created_at and day_start <= r.created_at < day_end
        ]

    # Get commit records for this date range
    all_commits = []
    seen_repos = set()

    for mr in mr_records:
        seen_repos.add(mr.repo_url)
        try:
            commits = knowledge_base.get_commits_by_mr(mr.repo_url, mr.mr_id)
            all_commits.extend(commits)
        except Exception as e:
            logger.debug("Failed to get commits for MR !%d: %e", mr.mr_id, e)

    # If a specific repo is requested, also get commits directly
    if repo_url and repo_url not in seen_repos:
        try:
            repo_commits = knowledge_base.get_commits_by_date_range(
                repo_url, day_start, day_end,
            )
            all_commits.extend(repo_commits)
            seen_repos.add(repo_url)
        except Exception as e:
            logger.debug("Failed to get commits by date range: %s", e)

    # --- Build per-developer stats ---
    dev_stats: dict[str, dict] = {}
    for c in all_commits:
        name = c.author_name or "unknown"
        if name not in dev_stats:
            dev_stats[name] = {
                "author_name": name,
                "author_email": c.author_email or "",
                "commits": 0,
                "additions": 0,
                "deletions": 0,
                "files_changed": 0,
                "repos": set(),
            }
        dev_stats[name]["commits"] += 1
        dev_stats[name]["additions"] += c.additions
        dev_stats[name]["deletions"] += c.deletions
        dev_stats[name]["files_changed"] += c.files_changed
        dev_stats[name]["repos"].add(c.repo_url)

    # --- Build per-repo stats ---
    repo_stats: dict[str, dict] = {}
    for mr in mr_records:
        repo = mr.repo_url
        if repo not in repo_stats:
            repo_stats[repo] = {
                "repo_url": repo,
                "mr_merged": 0,
                "total_additions": 0,
                "total_deletions": 0,
                "total_commits": 0,
                "findings_count": 0,
                "developers": set(),
            }
        repo_stats[repo]["mr_merged"] += 1
        repo_stats[repo]["total_commits"] += len(all_commits)
        if mr.author:
            repo_stats[repo]["developers"].add(mr.author)

    # Find risks for each MR
    import json
    total_risks = 0
    for mr in mr_records:
        if mr.risks:
            try:
                risks = json.loads(mr.risks)
                total_risks += len(risks)
            except (json.JSONDecodeError, TypeError):
                pass

    # --- Build response ---
    # Convert sets to lists for JSON serialization
    for dev in dev_stats.values():
        dev["repos"] = list(dev["repos"])
    for repo in repo_stats.values():
        repo["developers"] = list(repo["developers"])

    # Sort developers by commit count
    sorted_devs = sorted(dev_stats.values(), key=lambda x: -x["commits"])
    sorted_repos = sorted(repo_stats.values(), key=lambda x: -x["mr_merged"])

    # Summarize findings
    all_findings = []
    for mr in mr_records:
        if mr.risks:
            try:
                risks = json.loads(mr.risks)
                for r in risks:
                    all_findings.append({
                        "mr_id": mr.mr_id,
                        "mr_title": mr.mr_title[:60],
                        "severity": r.get("severity", ""),
                        "message": r.get("message", "")[:100],
                    })
            except (json.JSONDecodeError, TypeError):
                pass

    # Count merged vs opened MRs
    def _parse_dt(val):
        """Parse datetime from string or return as-is."""
        if isinstance(val, str):
            return datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
        return val

    merged_count = sum(
        1 for r in mr_records
        if r.merged_at and day_start <= _parse_dt(r.merged_at) < day_end
    )
    opened_count = len(mr_records) - merged_count

    report = {
        "date": date_str or report_date.strftime("%Y-%m-%d"),
        "generated_at": datetime.utcnow().isoformat(),
        "summary": {
            "total_mrs": len(mr_records),
            "mr_merged": merged_count,
            "mr_opened": opened_count,
            "total_commits": len(all_commits),
            "total_additions": sum(s["additions"] for s in dev_stats.values()),
            "total_deletions": sum(s["deletions"] for s in dev_stats.values()),
            "total_developers": len(dev_stats),
            "total_repos": len(repo_stats),
            "total_risks": total_risks,
        },
        "developers": sorted_devs,
        "repositories": sorted_repos,
        "mr_details": [
            {
                "mr_id": r.mr_id,
                "title": r.mr_title[:80],
                "author": r.author,
                "source_branch": r.source_branch,
                "target_branch": r.target_branch,
                "summary": r.summary[:200],
            }
            for r in mr_records[:50]
        ],
        "findings": all_findings[:50],
    }

    return report


@router.get("/trends")
async def trends(
    period: str = Query(default="weekly", description="Aggregation period: weekly or monthly"),
    count: int = Query(default=8, ge=1, le=52, description="Number of periods to look back"),
    repo_url: str = Query(default="", description="Filter by repository URL"),
):
    """Get trend data for code activity over time.

    Aggregates MR counts, commit counts, code changes, and security risks
    into weekly or monthly periods. Useful for visualizing project health
    and developer productivity over time.

    Args:
        period: Aggregation period - "weekly" (default) or "monthly".
        count: Number of periods. Default 8 weeks or 6 months.
        repo_url: Optional repo URL filter.
    """
    from app.services.trend_analyzer import TrendAnalyzer
    analyzer = TrendAnalyzer()

    if period == "monthly":
        if count > 12:
            count = 12
        data = analyzer.get_monthly_trends(count, repo_url)
    else:
        if count > 12:
            count = 12
        data = analyzer.get_weekly_trends(count, repo_url)

    summary = analyzer.get_trend_summary(repo_url)

    # Add scan task counts from task storage
    try:
        from app.services.storage import StorageService, TaskRecord
        from sqlalchemy import select, func
        from sqlalchemy.ext.asyncio import AsyncSession
        store = StorageService()
    except Exception:
        store = None

    # Normalize data fields for frontend compatibility
    normalized_data = []
    for item in data:
        normalized = dict(item)
        normalized["date"] = item.get("period", "")
        normalized["day"] = item.get("period", "")
        normalized["scan_count"] = item.get("mr_count", 0) + item.get("commit_count", 0)
        if "count" not in normalized:
            normalized["count"] = normalized["scan_count"]

        # Augment with actual scan task count from storage
        if store:
            try:
                start = item.get("start", "")
                end = item.get("end", "")
                if start:
                    from datetime import datetime
                    from sqlalchemy import and_
                    start_dt = datetime.fromisoformat(start)
                    end_dt = datetime.fromisoformat(end) if end else None
                    async with AsyncSession(store.engine) as session:
                        q = select(func.count(TaskRecord.id)).where(
                            and_(
                                TaskRecord.created_at >= start_dt,
                                TaskRecord.created_at < end_dt if end_dt else True,
                            )
                        )
                        result = await session.execute(q)
                        task_count = result.scalar() or 0
                        if task_count > 0:
                            normalized["scan_count"] = task_count
                            normalized["count"] = task_count
            except Exception:
                pass

        normalized_data.append(normalized)

    # If no data has non-zero scan counts, add current period with actual task data
    if not any(d.get("scan_count", 0) > 0 for d in normalized_data):
        try:
            from app.services.storage import StorageService
            from sqlalchemy import select, func
            from sqlalchemy.ext.asyncio import AsyncSession
            from app.services.storage import TaskRecord
            store = StorageService()
            from datetime import datetime, timedelta
            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            async with AsyncSession(store.engine) as session:
                q = select(func.count(TaskRecord.id)).where(TaskRecord.created_at >= today_start)
                result = await session.execute(q)
                today_count = result.scalar() or 0
            if today_count > 0:
                today_label = now.strftime("%m/%d")
                normalized_data.append({
                    "period": today_label,
                    "date": today_label,
                    "day": today_label,
                    "scan_count": today_count,
                    "count": today_count,
                    "start": today_start.isoformat(),
                    "end": now.isoformat(),
                    "mr_count": 0,
                    "commit_count": 0,
                    "developer_count": 0,
                    "risk_count": 0,
                })
        except Exception:
            pass

    return {
        "period": period,
        "count": len(data),
        "data": normalized_data,
        "summary": summary,
    }

