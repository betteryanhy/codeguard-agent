"""Auto-discovery service: scans GitLab for projects and registers webhooks."""

import logging
from typing import Optional

from app.config import settings
from app.services.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)

# Project type classification priority (higher = more specific)
PROJECT_TYPE_PRIORITY = [
    "iac_terraform",
    "k8s_manifest",
    "go",
    "java",
    "node",
    "python",
    "rust",
    "container",
    "ruby",
    "php",
    "dotnet",
]


def classify_project(files: list[str]) -> dict:
    """Classify a project by its file structure.

    Args:
        files: List of file paths in the project repository.

    Returns:
        dict with "types" (list of detected types) and "primary_type".
    """
    types = set()
    file_names = {f.lower() for f in files}
    lower_files = [f.lower() for f in files]

    # IaC / Terraform
    if any(f.endswith(".tf") or f.endswith(".tfvars") for f in lower_files):
        types.add("iac_terraform")

    # Container
    if "dockerfile" in file_names or any(f.endswith(".dockerfile") for f in lower_files):
        types.add("container")

    # K8s manifests
    if any(
        f.endswith((".yaml", ".yml")) and
        any(kw in f for kw in ("k8s", "kubernetes", "deployment", "service", "ingress"))
        for f in lower_files
    ):
        types.add("k8s_manifest")

    # Go
    if "go.mod" in file_names or "go.sum" in file_names:
        types.add("go")

    # Node.js
    if any(f in file_names for f in ("package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml")):
        types.add("node")

    # Python
    if any(f in file_names for f in ("requirements.txt", "pipfile", "setup.py", "pyproject.toml")):
        types.add("python")

    # Java
    if any(f in file_names for f in ("pom.xml", "build.gradle", "build.gradle.kts")):
        types.add("java")

    # Rust
    if "cargo.toml" in file_names or "cargo.lock" in file_names:
        types.add("rust")

    # Ruby
    if "gemfile" in file_names or "gemfile.lock" in file_names:
        types.add("ruby")

    # PHP
    if "composer.json" in file_names or "composer.lock" in file_names:
        types.add("php")

    # .NET
    if any(f.endswith((".csproj", ".sln", ".vbproj")) for f in lower_files):
        types.add("dotnet")

    return {
        "types": sorted(types) if types else ["unknown"],
        "primary_type": _determine_primary(types),
    }


def _determine_primary(types: set) -> str:
    """Determine the primary project type based on priority ordering."""
    for t in PROJECT_TYPE_PRIORITY:
        if t in types:
            return t
    if types:
        return sorted(types)[0]
    return "unknown"


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
        description: str = "",
        webhook_id: Optional[int] = None,
        webhook_url: str = "",
        registered: bool = False,
        project_types: Optional[list[str]] = None,
        primary_type: str = "unknown",
    ):
        self.project_id = project_id
        self.name = name
        self.name_with_namespace = name_with_namespace
        self.path_with_namespace = path_with_namespace
        self.http_url_to_repo = http_url_to_repo
        self.visibility = visibility
        self.default_branch = default_branch
        self.description = description
        self.webhook_id = webhook_id
        self.webhook_url = webhook_url
        self.registered = registered
        self.project_types = project_types or ["unknown"]
        self.primary_type = primary_type


class DiscoveryService:
    """Scans GitLab for accessible projects and auto-registers webhooks."""

    @staticmethod
    def _fix_repo_url(url: str) -> str:
        """Replace GitLab Docker-internal hostname with externally accessible address."""
        return url.replace("http://gitlab/", "http://127.0.0.1:8081/").replace("http://gitlab:80/", "http://127.0.0.1:8081/")

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

    def _fetch_project_files(self, project_id: int) -> list[str]:
        """Fetch file list for a project via GitLab API."""
        try:
            return self._client.get_project_files(project_id)
        except Exception as e:
            logger.debug("Could not fetch files for project %d: %s", project_id, e)
            return []

    def _enrich_with_classification(self, dp: DiscoveredProject):
        """Fetch project files and classify the project."""
        files = self._fetch_project_files(dp.project_id)
        if files:
            classification = classify_project(files)
            dp.project_types = classification["types"]
            dp.primary_type = classification["primary_type"]

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
                http_url_to_repo=DiscoveryService._fix_repo_url(p.get("http_url_to_repo", "")),
                visibility=p.get("visibility", ""),
                default_branch=p.get("default_branch", ""),
                description=p.get("description", ""),
            )
            self._enrich_with_classification(dp)
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
                http_url_to_repo=self._fix_repo_url(project_data.get("http_url_to_repo", repo_url)),
                visibility=project_data.get("visibility", ""),
                default_branch=project_data.get("default_branch", ""),
                description=project_data.get("description", ""),
            )
            self._enrich_with_classification(dp)
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
                "description": dp.description,
                "webhook_id": dp.webhook_id,
                "registered": dp.registered,
                "project_types": dp.project_types,
                "primary_type": dp.primary_type,
            }
            for dp in self._discovered.values()
        ]

    # ------------------------------------------------------------------
    # Real-time sync (used by system hooks and background sync)
    # ------------------------------------------------------------------

    def add_project_by_id(self, project_id: int) -> Optional[DiscoveredProject]:
        """Fetch a single project from GitLab and add it to the cache.

        Used by system hooks when a project_create event is received.
        Auto-registers webhook for the new project.
        """
        try:
            url = f"{self._client._gitlab_url}/api/v4/projects/{project_id}"
            import httpx
            with httpx.Client() as client:
                resp = client.get(url, headers=self._client._get_headers())
                resp.raise_for_status()
                p = resp.json()

            # Skip projects marked for deletion
            if p.get("marked_for_deletion_at"):
                logger.info("Project %d is marked for deletion, skipping", project_id)
                return None

            dp = DiscoveredProject(
                project_id=p["id"],
                name=p.get("name", ""),
                name_with_namespace=p.get("name_with_namespace", ""),
                path_with_namespace=p.get("path_with_namespace", ""),
                http_url_to_repo=self._fix_repo_url(p.get("http_url_to_repo", "")),
                visibility=p.get("visibility", ""),
                default_branch=p.get("default_branch", ""),
                description=p.get("description", ""),
            )
            self._enrich_with_classification(dp)
            self._discovered[project_id] = dp
            return dp
        except Exception as e:
            logger.warning("Failed to add project %d: %s", project_id, e)
            return None

    def remove_project(self, project_id: int) -> bool:
        """Remove a project from the cache.

        Used by system hooks when a project_destroy event is received.
        """
        if project_id in self._discovered:
            del self._discovered[project_id]
            logger.info("Removed project %d from cache", project_id)
            return True
        return False

    def sync_with_gitlab(self) -> dict:
        """Full sync: detect added and removed projects.

        Compares current GitLab project list with cached state.
        Auto-registers webhooks for new projects.
        Removes projects that no longer exist in GitLab.

        Returns a dict with added/removed/unchanged counts.
        """
        current = self._client.list_projects()
        current_ids = {p["id"] for p in current}
        cached_ids = set(self._discovered.keys())

        added_ids = current_ids - cached_ids
        removed_ids = cached_ids - current_ids

        # Remove projects that no longer exist in GitLab
        for pid in removed_ids:
            dp = self._discovered.get(pid)
            name = dp.name_with_namespace if dp else str(pid)
            del self._discovered[pid]
            logger.info("Sync: removed deleted project %s (ID=%d)", name, pid)

        # Add new projects
        added_count = 0
        for p in current:
            if p["id"] in added_ids:
                dp = DiscoveredProject(
                    project_id=p["id"],
                    name=p.get("name", ""),
                    name_with_namespace=p.get("name_with_namespace", ""),
                    path_with_namespace=p.get("path_with_namespace", ""),
                    http_url_to_repo=self._fix_repo_url(p.get("http_url_to_repo", "")),
                    visibility=p.get("visibility", ""),
                    default_branch=p.get("default_branch", ""),
                    description=p.get("description", ""),
                )
                self._enrich_with_classification(dp)
                self._discovered[p["id"]] = dp
                added_count += 1
                logger.info("Sync: discovered new project %s (ID=%d)", dp.name_with_namespace, p["id"])
                # Auto-register webhook
                try:
                    self.ensure_single_webhook(p["id"])
                except Exception as e:
                    logger.warning("Sync: failed to register webhook for %d: %s", p["id"], e)

        result = {
            "total_before": len(cached_ids),
            "total_after": len(self._discovered),
            "added": added_count,
            "removed": len(removed_ids),
            "unchanged": len(current_ids & cached_ids),
        }
        logger.info("Sync complete: %s", result)
        return result

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
