"""Scan strategy API - per-repo scanning policy configuration."""

import logging
from fastapi import APIRouter, Query, HTTPException, Request, Body
from app.services.scan_strategy import ScanStrategy, ScanStrategyManager, VALID_LEVELS, DEFAULT_STRATEGY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])


def _get_mgr(request: Request):
    mgr = getattr(request.app.state, "scan_strategy_manager", None)
    if not mgr:
        raise HTTPException(status_code=503, detail="Strategy manager not initialized")
    return mgr


@router.get("/default")
async def get_default_strategy(request: Request):
    """Get the global default scan strategy."""
    mgr = _get_mgr(request)
    strategy = mgr.get_strategy("__default__")
    return strategy.to_dict()


@router.put("/default")
async def update_default_strategy(request: Request, config: dict = Body(...)):
    """Update the global default scan strategy."""
    mgr = _get_mgr(request)
    current = mgr.get_strategy("__default__")

    # Apply updates
    for key, val in config.items():
        if hasattr(current, key):
            setattr(current, key, val)

    if current.scan_level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid scan_level: {current.scan_level}. Must be one of {VALID_LEVELS}")

    mgr.save_strategy(current)
    return {"status": "ok", "strategy": current.to_dict()}


@router.get("/repos")
async def list_all_strategies(request: Request):
    """List all repository-specific strategies."""
    mgr = _get_mgr(request)
    strategies = mgr.list_strategies()
    return {
        "total": len(strategies),
        "strategies": [s.to_dict() for s in strategies],
    }


@router.get("/repos/{repo_url:path}")
async def get_repo_strategy(request: Request, repo_url: str):
    """Get strategy for a specific repository."""
    mgr = _get_mgr(request)
    strategy = mgr.get_strategy(repo_url)
    return strategy.to_dict()


@router.put("/repos/{repo_url:path}")
async def set_repo_strategy(
    request: Request,
    repo_url: str,
    config: dict = Body(...),
):
    """Create or update strategy for a specific repository.

    Only provided fields will be updated; missing fields keep defaults.
    """
    mgr = _get_mgr(request)
    current = mgr.get_strategy(repo_url)

    # If this repo has no custom strategy yet, copy defaults first
    if current.repo_url != repo_url:
        default = mgr.get_strategy("__default__")
        current = ScanStrategy(repo_url=repo_url)
        # Copy default values
        for field in ScanStrategy.__dataclass_fields__:
            if field not in ("repo_url", "created_at", "updated_at"):
                setattr(current, field, getattr(default, field))

    # Apply updates
    for key, val in config.items():
        if hasattr(current, key):
            setattr(current, key, val)

    if current.scan_level not in VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid scan_level: {current.scan_level}")

    mgr.save_strategy(current)
    return {"status": "ok", "strategy": current.to_dict()}


@router.delete("/repos/{repo_url:path}")
async def delete_repo_strategy(request: Request, repo_url: str):
    """Delete a repository-specific strategy (revert to default)."""
    mgr = _get_mgr(request)
    ok = mgr.delete_strategy(repo_url)
    if not ok:
        raise HTTPException(status_code=404, detail="Strategy not found or cannot be deleted")
    return {"status": "deleted", "repo_url": repo_url}
