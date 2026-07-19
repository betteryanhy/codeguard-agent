from fastapi import APIRouter, HTTPException
from app.models.repository import RepoConfig

router = APIRouter(prefix="/api/v1/config", tags=["config"])

# In-memory config store
_configs: dict[str, RepoConfig] = {}


@router.get("/repositories")
async def list_repositories():
    """List all registered repositories."""
    return [
        {
            "repo_url": cfg.repo_url,
            "active": cfg.active,
            "enabled_engines": cfg.enabled_engines,
        }
        for cfg in _configs.values()
    ]


@router.post("/repositories")
async def register_repository(config: RepoConfig):
    """Register a repository for MR monitoring."""
    if config.repo_url in _configs:
        raise HTTPException(status_code=409, detail="Repository already registered")
    _configs[config.repo_url] = config
    return {"status": "registered", "repo_url": config.repo_url}


@router.get("/repositories/{repo_id}")
async def get_repository(repo_id: str):
    """Get repository configuration by URL or ID."""
    for url, cfg in _configs.items():
        if url == repo_id or url.endswith("/" + repo_id):
            return cfg
    raise HTTPException(status_code=404, detail="Repository not found")


@router.post("/repositories/{repo_id}/disable")
async def disable_repository(repo_id: str):
    """Disable monitoring for a repository (NOT delete)."""
    for url, cfg in _configs.items():
        if url == repo_id or url.endswith("/" + repo_id):
            cfg.active = False
            return {"status": "disabled", "repo_url": url}
    raise HTTPException(status_code=404, detail="Repository not found")


@router.post("/repositories/{repo_id}/enable")
async def enable_repository(repo_id: str):
    """Re-enable monitoring for a repository."""
    for url, cfg in _configs.items():
        if url == repo_id or url.endswith("/" + repo_id):
            cfg.active = True
            return {"status": "enabled", "repo_url": url}
    raise HTTPException(status_code=404, detail="Repository not found")
