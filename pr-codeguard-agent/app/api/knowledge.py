"""Knowledge base API - semantic search and knowledge query endpoints."""

import json
import logging
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException, Request

from app.knowledge.sqlite_store import SqliteStore
from app.knowledge.schemas import MrRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


def _get_kb(request: Request):
    """Get knowledge base from app state."""
    kb = getattr(request.app.state, "knowledge_base", None)
    if not kb:
        raise HTTPException(status_code=503, detail="Knowledge base not initialized")
    return kb


@router.get("/search")
async def search_knowledge(
    request: Request,
    q: str = Query(..., description="Search query"),
    scope: str = Query(default="all", description="Search scope: all, code, mr"),
    n_results: int = Query(default=5, ge=1, le=20, description="Number of results"),
    repo_url: str = Query(default="", description="Filter by repository URL"),
):
    """Semantic search across the knowledge base.

    Supports three scopes:
    - all (default): search both code chunks and MR records
    - code: search code chunks only
    - mr: search MR records only

    Returns ranked results with relevance scores.
    """
    kb = _get_kb(request)
    results = []

    if scope in ("all", "mr"):
        mr_filter = {"repo_url": repo_url} if repo_url else None
        try:
            mr_results = kb.search_mr(q, n_results, filter=mr_filter)
            for r in mr_results:
                results.append({
                    "type": "mr",
                    "id": r.get("id", ""),
                    "document": r.get("document", ""),
                    "metadata": r.get("metadata", {}),
                    "score": r.get("score", 0),
                })
        except Exception as e:
            logger.warning("MR search failed: %s", e)

    if scope in ("all", "code"):
        code_filter = {"repo_url": repo_url} if repo_url else None
        try:
            code_results = kb.search_code(q, n_results, filter=code_filter)
            for r in code_results:
                results.append({
                    "type": "code",
                    "id": r.get("id", ""),
                    "document": r.get("document", ""),
                    "metadata": r.get("metadata", {}),
                    "score": r.get("score", 0),
                })
        except Exception as e:
            logger.warning("Code search failed: %s", e)

    # Sort by score descending
    results.sort(key=lambda r: r.get("score", 0), reverse=True)

    return {
        "query": q,
        "scope": scope,
        "total": len(results),
        "results": results[:n_results],
    }


@router.get("/mrs")
async def list_mr_knowledge(
    request: Request,
    repo_url: str = Query(default="", description="Filter by repository URL"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """List recent MR knowledge records."""
    kb = _get_kb(request)

    if repo_url:
        records = kb.get_mr_records(repo_url, limit=limit)
    else:
        # Get records from all repos via SQLite
        store = SqliteStore()
        conn = store._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM mr_records ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            records = [MrRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    result_list = []
    for r in records:
        risks = json.loads(r.risks) if r.risks else []
        # Parse merged_at from string if needed
        merged_at = r.merged_at
        if isinstance(merged_at, str):
            merged_at = datetime.fromisoformat(merged_at.replace("Z", "+00:00")).replace(tzinfo=None)
        result_list.append({
            "mr_id": r.mr_id,
            "title": r.mr_title,
            "source_branch": r.source_branch,
            "target_branch": r.target_branch,
            "author": r.author,
            "merged_at": merged_at.isoformat() if merged_at else None,
            "summary": r.summary,
            "risk_count": len(risks),
        })

    return {"total": len(result_list), "records": result_list}
