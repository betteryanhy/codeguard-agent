"""Developer analytics service: queries GitLab for per-developer stats."""

import logging
import httpx
from collections import defaultdict
from typing import Optional

from app.services.gitlab_client import GitLabClient
from app.services.discovery_service import DiscoveryService

logger = logging.getLogger(__name__)


class DeveloperService:
    """Provides developer-level analytics from GitLab data."""

    def __init__(self, discovery: Optional[DiscoveryService] = None):
        self._client = GitLabClient()
        self._discovery = discovery

    def _get_active_projects(self) -> list[dict]:
        """Get active GitLab projects."""
        if self._discovery:
            return self._discovery.list_discovered()
        return self._client.list_projects()

    def get_developer_stats(self) -> list[dict]:
        """Get commit statistics grouped by developer across all projects.

        Returns list sorted by commit count descending:
          [{author, commit_count, projects, total_additions, total_deletions}]
        """
        projects = self._get_active_projects()
        author_data = defaultdict(lambda: {
            "author": "",
            "commit_count": 0,
            "projects": set(),
            "total_additions": 0,
            "total_deletions": 0,
        })

        with httpx.Client() as client:
            for p in projects:
                pid = p.get("project_id") or p.get("id")
                if not pid:
                    continue
                try:
                    url = f"{self._client._gitlab_url}/api/v4/projects/{pid}/repository/commits?per_page=100"
                    resp = client.get(url, headers=self._client._get_headers())
                    if resp.status_code != 200:
                        continue
                    commits = resp.json()
                    for c in commits:
                        author = c.get("author_name", "unknown")
                        entry = author_data[author]
                        entry["author"] = author
                        entry["commit_count"] += 1
                        entry["projects"].add(p.get("path_with_namespace", str(pid)))

                        # Get detailed stats per commit
                        sha = c.get("id", "")
                        try:
                            detail_url = f"{self._client._gitlab_url}/api/v4/projects/{pid}/repository/commits/{sha}"
                            dr = client.get(detail_url, headers=self._client._get_headers())
                            if dr.status_code == 200:
                                stats = dr.json().get("stats", {})
                                entry["total_additions"] += stats.get("additions", 0)
                                entry["total_deletions"] += stats.get("deletions", 0)
                        except Exception:
                            pass
                except Exception as e:
                    logger.warning("Failed to fetch commits for project %d: %s", pid, e)

        result = []
        for author, data in sorted(author_data.items(), key=lambda x: -x[1]["commit_count"]):
            result.append({
                "author": data["author"],
                "commit_count": data["commit_count"],
                "projects": sorted(data["projects"]),
                "project_count": len(data["projects"]),
                "total_additions": data["total_additions"],
                "total_deletions": data["total_deletions"],
            })
        return result

    def get_developer_commits(self, author_name: str, limit: int = 20) -> list[dict]:
        """Get recent commits by a specific developer across all projects.

        Returns list sorted by date descending:
          [{short_id, title, project, date, additions, deletions}]
        """
        projects = self._get_active_projects()
        all_commits = []

        with httpx.Client() as client:
            for p in projects:
                pid = p.get("project_id") or p.get("id")
                if not pid:
                    continue
                try:
                    url = f"{self._client._gitlab_url}/api/v4/projects/{pid}/repository/commits?per_page=50"
                    resp = client.get(url, headers=self._client._get_headers())
                    if resp.status_code != 200:
                        continue
                    commits = resp.json()
                    for c in commits:
                        if c.get("author_name", "").lower() != author_name.lower():
                            continue
                        entry = {
                            "short_id": c.get("short_id", ""),
                            "title": c.get("title", ""),
                            "project": p.get("path_with_namespace", str(pid)),
                            "date": c.get("committed_date", "")[:19],
                            "additions": 0,
                            "deletions": 0,
                        }
                        # Get detailed stats
                        sha = c.get("id", "")
                        try:
                            detail_url = f"{self._client._gitlab_url}/api/v4/projects/{pid}/repository/commits/{sha}"
                            dr = client.get(detail_url, headers=self._client._get_headers())
                            if dr.status_code == 200:
                                stats = dr.json().get("stats", {})
                                entry["additions"] = stats.get("additions", 0)
                                entry["deletions"] = stats.get("deletions", 0)
                        except Exception:
                            pass
                        all_commits.append(entry)
                except Exception as e:
                    logger.warning("Failed to fetch commits for project %d: %s", pid, e)

        all_commits.sort(key=lambda x: x["date"], reverse=True)
        return all_commits[:limit]

    def get_merged_features(self, project_path: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Get merged MRs with descriptions across projects.

        Returns list sorted by update date descending:
          [{mr_id, title, description, author, project, merged_at}]
        """
        projects = self._get_active_projects()
        if project_path:
            projects = [p for p in projects if project_path in (p.get("path_with_namespace", "") or "")]

        all_mrs = []

        with httpx.Client() as client:
            for p in projects:
                pid = p.get("project_id") or p.get("id")
                if not pid:
                    continue
                try:
                    url = f"{self._client._gitlab_url}/api/v4/projects/{pid}/merge_requests?state=merged&per_page=20&order_by=updated_at"
                    resp = client.get(url, headers=self._client._get_headers())
                    if resp.status_code != 200:
                        continue
                    mrs = resp.json()
                    for mr in mrs:
                        author = mr.get("author", {})
                        all_mrs.append({
                            "mr_id": mr.get("iid", ""),
                            "title": mr.get("title", ""),
                            "description": (mr.get("description", "") or "")[:200],
                            "author": author.get("name", author.get("username", "?")),
                            "project": p.get("path_with_namespace", str(pid)),
                            "merged_at": (mr.get("merged_at") or "")[:19],
                        })
                except Exception as e:
                    logger.warning("Failed to fetch MRs for project %d: %s", pid, e)

        all_mrs.sort(key=lambda x: x["merged_at"], reverse=True)
        return all_mrs[:limit]

    def get_all_developers(self) -> list[str]:
        """Get list of all unique developer names from commits."""
        stats = self.get_developer_stats()
        return [s["author"] for s in stats]
