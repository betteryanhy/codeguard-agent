"""Query API - natural language Q&A about developer activity.

Provides endpoints for querying the knowledge base using natural language.
Supports questions about commits, MRs, file changes, and developer activity.

Endpoints:
  POST /api/v1/query - Ask a natural language question
  GET  /api/v1/query/trends - Get recent activity trends
"""

import logging
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.query_engine import QueryEngine
from app.knowledge.knowledge_base import KnowledgeBase
from app.services.daily_digest import DailyDigest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["query"])

# Shared engine instance
_query_engine: QueryEngine | None = None


def get_engine() -> QueryEngine:
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine()
    return _query_engine


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="Natural language question")
    repo_url: str = Field("", description="Optional: filter by repository URL")


class QueryResponse(BaseModel):
    question: str
    answer: str
    source_count: int
    sources: list[dict]


@router.post("/query", response_model=QueryResponse)
async def ask_question(request: QueryRequest):
    """Ask a natural language question about code activity.

    Examples:
      - "user_service.go 这个文件最近谁改过？"
      - "payment 模块上周有什么变更？"
      - "张三最近提交了什么？"
      - "昨天有什么高风险MR？"
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    engine = get_engine()
    result = await engine.query(request.question)

    return QueryResponse(
        question=result["question"],
        answer=result["answer"],
        source_count=result["source_count"],
        sources=result["sources"],
    )


@router.get("/query/trends")
async def get_activity_trends(days: int = 7):
    """Get recent developer activity trends."""
    kb = KnowledgeBase()
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    try:
        commits = kb.get_all_commits_by_date_range(start_date, end_date)
    except Exception as e:
        logger.warning("Failed to get commit trends: %s", e)
        commits = []

    # Group by author
    author_stats: dict[str, dict] = {}
    for c in commits:
        name = c.author_name or "unknown"
        if name not in author_stats:
            author_stats[name] = {
                "name": name,
                "commit_count": 0,
                "total_changes": 0,
                "first_commit": "",
                "last_commit": "",
            }
        author_stats[name]["commit_count"] += 1
        author_stats[name]["total_changes"] += c.total_changes or 0
        if c.committed_date:
            d_str = str(c.committed_date)
            if not author_stats[name]["first_commit"] or d_str < author_stats[name]["first_commit"]:
                author_stats[name]["first_commit"] = d_str
            if not author_stats[name]["last_commit"] or d_str > author_stats[name]["last_commit"]:
                author_stats[name]["last_commit"] = d_str

    return {
        "days": days,
        "total_commits": len(commits),
        "total_authors": len(author_stats),
        "authors": sorted(
            author_stats.values(),
            key=lambda x: x["commit_count"],
            reverse=True,
        ),
    }


@router.post("/digest")
async def generate_digest(date_str: str = Query("", alias="date", description="Report date (YYYY-MM-DD, default: yesterday)")):
    """Generate a daily digest for a specific date."""
    digest = DailyDigest()
    report_date = None
    if date_str:
        from datetime import date as date_type
        try:
            report_date = date_type.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD.")
    data = await digest.generate(report_date)
    return data


@router.post("/digest/send")
async def send_daily_report(date_str: str = Query("", alias="date", description="Report date (YYYY-MM-DD, default: yesterday)")):
    """Generate and send daily report email immediately."""
    from datetime import date as date_type
    report_date = None
    if date_str:
        try:
            report_date = date_type.fromisoformat(date_str)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}. Use YYYY-MM-DD.")

    from app.services.email_scheduler import EmailScheduler
    scheduler = EmailScheduler()
    result = await scheduler.send_daily_report(report_date)
    if result is None:
        raise HTTPException(
            status_code=400,
            detail="Email not configured. Set ALERT_SMTP_HOST, ALERT_EMAIL_FROM, and ALERT_EMAIL_TO in .env",
        )
    return result
