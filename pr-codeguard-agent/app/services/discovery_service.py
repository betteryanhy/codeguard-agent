"""Auto-discovery service: scans GitLab for projects and registers webhooks."""

import logging
from typing import Optional

from app.config import settings
from app.services.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


class DiscoveredProject:
    """Represents a project discovered via GitLab API."""

    def __init__(
        self,
        project_id: int,
        name: str,
        name_with_namespace: str,
        path_with_namespace: str,
        http_url_to_repo: str,
        visibility: str,
        default_branch: str,
        webhook_id: Optional[int] = None,
        webhook_url: str = "",
        registered: bool = False,
    ):
        self.project_id = project_id
        self.name = name
        self.name_with_namespace = name_with_namespace
        self.path_with_namespace = path_with_namespace
        self.http_url_to_repo = http_url_to_repo
        self.visibility = visibility
        self.default_branch = default_branch
        self.webhook_id = webhook_id
        self.webhook_url = webhook_url
        self.registered = registered


class DiscoveryService:
    """Scans GitLab for accessible projects and auto-registers webhooks."""

    def __init__(self):
        self._client = GitLabClient()
        self._discovered: dict[int, DiscoveredProject] = {}
        self._agent_url = f"http://{settings.host}:{settings.port}"

    def set_agent_url(self, host: str, port: int):
        """Override the agent's public URL used for webhook callbacks."""
        self._agent_url = f"http://{host}:{port}"

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def scan_all(self) -> list[DiscoveredProject]:
        """Scan all accessible GitLab projects and cache them."""
        projects = self._client.list_projects()
        discovered = []

        for p in projects:
            dp = DiscoveredProject(
                project_id=p["id"],
                name=p.get("name", ""),
                name_with_namespace=p.get("name_with_namespace", ""),
                path_with_namespace=p.get("path_with_namespace", ""),
                http_url_to_repo=p.get("http_url_to_repo", ""),
                visibility=p.get("visibility", ""),
                default_branch=p.get("default_branch", ""),
            )
            self._discovered[p["id"]] = dp
            discovered.append(dp)

        logger.info("Discovered %d projects from GitLab", len(discovered))
        return discovered

    def scan_single(self, repo_url: str) -> Optional[DiscoveredProject]:
        """Discover a single project by its repository URL."""
        try:
            project_data = self._client.get_project_by_url(repo_url)
            if not project_data:
                logger.warning("Project not found: %s", repo_url)
                return None

            dp = DiscoveredProject(
                project_id=project_data["id"],
                name=project_data.get("name", ""),
                name_with_namespace=project_data.get("name_with_namespace", ""),
                path_with_namespace=project_data.get("path_with_namespace", ""),
                http_url_to_repo=project_data.get("http_url_to_repo", repo_url),
                visibility=project_data.get("visibility", ""),
                default_branch=project_data.get("default_branch", ""),
            )
            self._discovered[project_data["id"]] = dp
            return dp
        except Exception as e:
            logger.warning("Failed to discover project %s: %s", repo_url, e)
            return None

    # ------------------------------------------------------------------
    # Webhook management
    # ------------------------------------------------------------------

    def ensure_webhooks(self, webhook_base_url: str = "") -> dict:
        """Ensure every discovered project has a webhook pointing to this agent.

        Returns summary dict with total / already_registered / registered / failed / skipped counts.
        """
        base_url = webhook_base_url or self._agent_url
        webhook_url = f"{base_url.rstrip('/')}/api/v1/webhook/gitlab"

        stats = {
            "total": 0,
            "already_registered": 0,
            "registered": 0,
            "failed": 0,
            "skipped": 0,
        }

        for pid, dp in self._discovered.items():
            stats["total"] += 1

            if not dp.http_url_to_repo:
                stats["skipped"] += 1
                continue

            try:
                hooks = self._client.list_webhooks(pid)
                existing = [h for h in hooks if webhook_url in h.get("url", "")]

                if existing:
                    dp.webhook_id = existing[0]["id"]
                    dp.webhook_url = webhook_url
                    dp.registered = True
                    stats["already_registered"] += 1
                    continue

                # Create new webhook
                secret = settings.webhook_secret
                result = self._client.create_webhook(pid, webhook_url, secret)
                dp.webhook_id = result.get("id")
                dp.webhook_url = webhook_url
                dp.registered = True
                stats["registered"] += 1
                logger.info(
                    "Registered webhook for project %d (%s)",
                    pid, dp.name_with_namespace,
                )

            except Exception as e:
                logger.warning("Failed to process webhook for project %d: %s", pid, e)
                stats["failed"] += 1

        return stats

    def ensure_single_webhook(self, project_id: int, webhook_base_url: str = "") -> bool:
        """Ensure a single project has a webhook registered."""
        base_url = webhook_base_url or self._agent_url
        webhook_url = f"{base_url.rstrip('/')}/api/v1/webhook/gitlab"

        dp = self._discovered.get(project_id)
        if not dp:
            logger.warning("Project %d not in discovered list", project_id)
            return False

        try:
            hooks = self._client.list_webhooks(project_id)
            existing = [h for h in hooks if webhook_url in h.get("url", "")]

            if existing:
                dp.webhook_id = existing[0]["id"]
                dp.webhook_url = webhook_url
                dp.registered = True
                return True

            secret = settings.webhook_secret
            result = self._client.create_webhook(project_id, webhook_url, secret)
            dp.webhook_id = result.get("id")
            dp.webhook_url = webhook_url
            dp.registered = True
            logger.info("Registered webhook for project %d (%s)", project_id, dp.name_with_namespace)
            return True

        except Exception as e:
            logger.warning("Failed to register webhook for project %d: %s", project_id, e)
            return False

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_discovered(self) -> list[dict]:
        """List all discovered projects with their webhook status."""
        return [
            {
                "project_id": dp.project_id,
                "name": dp.name,
                "name_with_namespace": dp.name_with_namespace,
                "path_with_namespace": dp.path_with_namespace,
                "http_url_to_repo": dp.http_url_to_repo,
                "visibility": dp.visibility,
                "default_branch": dp.default_branch,
                "webhook_id": dp.webhook_id,
                "registered": dp.registered,
            }
            for dp in self._discovered.values()
        ]

    def get_project_by_url(self, repo_url: str) -> Optional[DiscoveredProject]:
        """Find a discovered project by its HTTP URL."""
        norm = repo_url.rstrip("/")
        for dp in self._discovered.values():
            if dp.http_url_to_repo.rstrip("/") == norm:
                return dp
        return None

    def get_project_by_id(self, project_id: int) -> Optional[DiscoveredProject]:
        """Find a discovered project by its GitLab project ID."""
        return self._discovered.get(project_id)
