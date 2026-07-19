"""Trend analysis - aggregate historical data into weekly/monthly trends."""

import json
import logging
from datetime import datetime, timedelta, date
from typing import Optional

logger = logging.getLogger(__name__)


class PeriodData:
    """Data snapshot for a single time period (week or month)."""

    def __init__(self, label: str, start: datetime, end: datetime):
        self.label = label
        self.start = start
        self.end = end
        self.mr_count = 0
        self.mr_merged = 0
        self.commit_count = 0
        self.additions = 0
        self.deletions = 0
        self.developer_count = 0
        self.risk_count = 0
        self.critical_risk_count = 0
        self.developers: set[str] = set()

    def to_dict(self) -> dict:
        return {
            "period": self.label,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "mr_count": self.mr_count,
            "mr_merged": self.mr_merged,
            "commit_count": self.commit_count,
            "additions": self.additions,
            "deletions": self.deletions,
            "net_change": self.additions - self.deletions,
            "developer_count": self.developer_count,
            "risk_count": self.risk_count,
            "critical_risk_count": self.critical_risk_count,
        }


class TrendAnalyzer:
    """Aggregate knowledge base data into time-series trends."""

    def __init__(self, settings_path: Optional[str] = None):
        self._kb = None
        self._store = None
        self._settings_path = settings_path

    def _get_store(self):
        """Get SqliteStore - try app state first, then create standalone."""
        if self._store is not None:
            return self._store

        # Try getting from app knowledge_base
        kb = self._get_kb()
        if kb:
            self._store = kb.sqlite
            return self._store

        # Fallback: create standalone store
        from app.knowledge.sqlite_store import SqliteStore
        from app.config import settings
        self._store = SqliteStore(settings.knowledge_db_path)
        self._store.init_db()
        return self._store

    def _get_kb(self):
        """Get KnowledgeBase from app main if available."""
        if self._kb is None:
            try:
                from app.main import knowledge_base
                self._kb = knowledge_base
            except Exception:
                self._kb = None
        return self._kb

    # ------------------------------------------------------------------
    # Period builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_weekly_periods(count: int) -> list[PeriodData]:
        """Build N weekly periods ending at the current week."""
        today = datetime.utcnow()
        # Find the most recent Monday
        days_since_monday = today.weekday()
        this_monday = today - timedelta(days=days_since_monday)
        this_monday = this_monday.replace(hour=0, minute=0, second=0, microsecond=0)

        periods = []
        for i in range(count - 1, -1, -1):
            start = this_monday - timedelta(weeks=i)
            end = start + timedelta(weeks=1)
            label = start.strftime("%m/%d") + "周"
            periods.append(PeriodData(label, start, end))
        return periods

    @staticmethod
    def _build_monthly_periods(count: int) -> list[PeriodData]:
        """Build N monthly periods ending at the current month."""
        today = datetime.utcnow()
        current_month = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        periods = []
        for i in range(count - 1, -1, -1):
            year = current_month.year
            month = current_month.month - i
            while month < 1:
                month += 12
                year -= 1
            start = datetime(year, month, 1)
            if month == 12:
                end = datetime(year + 1, 1, 1)
            else:
                end = datetime(year, month + 1, 1)
            label = start.strftime("%Y年%m月")
            periods.append(PeriodData(label, start, end))
        return periods

    # ------------------------------------------------------------------
    # Data aggregation
    # ------------------------------------------------------------------

    def _fill_period(self, period: PeriodData, repo_url: str = ""):
        """Fill a single period with data from the knowledge base."""
        store = self._get_store()
        if not store:
            return

        try:
            # MR records in this period
            mrs = store.get_mr_records_by_date(period.start, period.end, repo_url)
            period.mr_count = len(mrs)

            # Merged count
            def _parse_dt(val):
                if isinstance(val, str):
                    return datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
                return val

            period.mr_merged = sum(
                1 for r in mrs
                if r.merged_at and period.start <= _parse_dt(r.merged_at) < period.end
            )

            # Risks from MRs
            for r in mrs:
                if r.author:
                    period.developers.add(r.author)
                if r.risks:
                    try:
                        risks = json.loads(r.risks)
                        period.risk_count += len(risks)
                        period.critical_risk_count += sum(
                            1 for risk in risks
                            if risk.get("severity", "").lower() in ("critical", "blocker")
                        )
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Commits in this period
            if repo_url:
                commits = store.get_commits_by_date_range(repo_url, period.start, period.end)
            else:
                commits = store.get_all_commits_by_date_range(period.start, period.end)

            period.commit_count = len(commits)
            period.additions = sum(c.additions for c in commits)
            period.deletions = sum(c.deletions for c in commits)
            for c in commits:
                if c.author_name:
                    period.developers.add(c.author_name)

            period.developer_count = len(period.developers)

        except Exception as e:
            logger.warning("Failed to fill period %s: %s", period.label, e)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_weekly_trends(self, weeks: int = 8, repo_url: str = "") -> list[dict]:
        """Get weekly trend data for the last N weeks."""
        periods = self._build_weekly_periods(weeks)
        for p in periods:
            self._fill_period(p, repo_url)
        return [p.to_dict() for p in periods]

    def get_monthly_trends(self, months: int = 6, repo_url: str = "") -> list[dict]:
        """Get monthly trend data for the last N months."""
        periods = self._build_monthly_periods(months)
        for p in periods:
            self._fill_period(p, repo_url)
        return [p.to_dict() for p in periods]

    def get_trend_summary(self, repo_url: str = "") -> dict:
        """Get a summary of the current trend direction.

        Compares the most recent complete period to the previous one.
        """
        weekly = self.get_weekly_trends(2, repo_url)
        monthly = self.get_monthly_trends(2, repo_url)

        summary = {
            "weekly": {
                "current": weekly[-1] if len(weekly) >= 1 else None,
                "previous": weekly[-2] if len(weekly) >= 2 else None,
            },
            "monthly": {
                "current": monthly[-1] if len(monthly) >= 1 else None,
                "previous": monthly[-2] if len(monthly) >= 2 else None,
            },
        }

        # Compute direction for each metric
        for period_name in ("weekly", "monthly"):
            cur = summary[period_name]["current"]
            prev = summary[period_name]["previous"]
            if cur and prev:
                direction = {}
                for key in ("mr_count", "commit_count", "additions", "risk_count", "critical_risk_count"):
                    diff = cur.get(key, 0) - prev.get(key, 0)
                    if diff > 0:
                        direction[key] = "up"
                    elif diff < 0:
                        direction[key] = "down"
                    else:
                        direction[key] = "stable"
                summary[period_name]["direction"] = direction

        return summary
