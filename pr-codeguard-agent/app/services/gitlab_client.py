import httpx
from urllib.parse import urlparse, quote

from app.config import settings


class GitLabClient:
    """GitLab API v4 client encapsulating all GitLab API calls."""

    def __init__(self, gitlab_url: str | None = None, api_token: str | None = None) -> None:
        self._gitlab_url = (gitlab_url or settings.gitlab_url).rstrip("/")
        self._api_token = api_token or settings.gitlab_api_token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self._api_token}

    @staticmethod
    def _extract_project_path(repo_url: str) -> str:
        """Extract the project path from a GitLab repository URL.

        Examples:
            "http://gitlab/root/my-project.git"       -> "root/my-project"
            "http://gitlab/root/my-project"            -> "root/my-project"
            "http://gitlab/group/subgroup/project.git" -> "group/subgroup/project"
            "http://gitlab.local:8080/ns/project.git"  -> "ns/project"
        """
        parsed = urlparse(repo_url)
        path = parsed.path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        return path

    def _get_encoded_project_path(self, repo_url: str) -> str:
        """URL-encode the project path for use in API requests."""
        project_path = self._extract_project_path(repo_url)
        return quote(project_path, safe="")

    def _build_url(self, repo_url: str, *segments: str | int) -> str:
        """Build a full API URL by joining path segments."""
        encoded_path = self._get_encoded_project_path(repo_url)
        path_parts = "/".join(str(s) for s in segments)
        return f"{self._gitlab_url}/api/v4/projects/{encoded_path}/{path_parts}"

    # ------------------------------------------------------------------
    # Public API methods
    # ------------------------------------------------------------------

    def get_project_id(self, repo_url: str) -> int:
        """GET /api/v4/projects/{encoded_path} -> project ID."""
        url = f"{self._gitlab_url}/api/v4/projects/{self._get_encoded_project_path(repo_url)}"
        with httpx.Client() as client:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()["id"]

    def get_mr_changes(self, repo_url: str, mr_id: int) -> dict:
        """GET /api/v4/projects/{id}/merge_requests/{mr_id}/changes."""
        url = self._build_url(repo_url, "merge_requests", mr_id, "changes")
        with httpx.Client() as client:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def post_mr_comment(self, repo_url: str, mr_id: int, body: str) -> dict:
        """POST /api/v4/projects/{id}/merge_requests/{mr_id}/notes."""
        url = self._build_url(repo_url, "merge_requests", mr_id, "notes")
        with httpx.Client() as client:
            resp = client.post(url, headers=self._get_headers(), json={"body": body})
            resp.raise_for_status()
            return resp.json()

    def get_mr_diffs(self, repo_url: str, mr_id: int) -> list[dict]:
        """GET /api/v4/projects/{id}/merge_requests/{mr_id}/diffs."""
        url = self._build_url(repo_url, "merge_requests", mr_id, "diffs")
        with httpx.Client() as client:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_mr_commits(self, repo_url: str, mr_id: int) -> list[dict]:
        """GET /api/v4/projects/{id}/merge_requests/{mr_id}/commits.

        Returns list of commits with: id, short_id, title, author_name,
        author_email, committed_date, stats (additions, deletions, total).
        """
        url = self._build_url(repo_url, "merge_requests", mr_id, "commits")
        with httpx.Client() as client:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_mr_details(self, repo_url: str, mr_id: int) -> dict:
        """GET /api/v4/projects/{id}/merge_requests/{mr_id}.

        Returns full MR details including: state, merge_status,
        merged_by, merge_user, etc.
        """
        url = self._build_url(repo_url, "merge_requests", mr_id)
        with httpx.Client() as client:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Project discovery
    # ------------------------------------------------------------------

    def list_projects(self, per_page: int = 50) -> list[dict]:
        """GET /api/v4/projects -> list all accessible projects.

        Fetches all pages automatically.
        Returns simplified list with: id, name, name_with_namespace,
        path_with_namespace, http_url_to_repo, visibility, default_branch.
        """
        all_projects = []
        page = 1

        with httpx.Client() as client:
            while True:
                url = (
                    f"{self._gitlab_url}/api/v4/projects"
                    f"?per_page={per_page}&page={page}&simple=true"
                )
                resp = client.get(url, headers=self._get_headers())
                resp.raise_for_status()

                page_data = resp.json()
                if not page_data:
                    break

                for p in page_data:
                    all_projects.append({
                        "id": p["id"],
                        "name": p.get("name", ""),
                        "name_with_namespace": p.get("name_with_namespace", ""),
                        "path_with_namespace": p.get("path_with_namespace", ""),
                        "http_url_to_repo": p.get("http_url_to_repo", ""),
                        "visibility": p.get("visibility", ""),
                        "default_branch": p.get("default_branch", ""),
                    })

                if len(page_data) < per_page:
                    break
                page += 1

        return all_projects

    def get_project_by_url(self, repo_url: str) -> dict | None:
        """GET /api/v4/projects/{encoded_path} -> get a single project by URL.

        Returns project details including id, web_url, visibility, etc.
        Returns None if the project is not found.
        """
        try:
            encoded_path = self._get_encoded_project_path(repo_url)
            url = f"{self._gitlab_url}/api/v4/projects/{encoded_path}"
            with httpx.Client() as client:
                resp = client.get(url, headers=self._get_headers())
                resp.raise_for_status()
                return resp.json()
        except Exception:
            # Fallback: try to find by searching
            project_path = self._extract_project_path(repo_url)
            url = f"{self._gitlab_url}/api/v4/projects?search={quote(project_path)}"
            with httpx.Client() as client:
                resp = client.get(url, headers=self._get_headers())
                resp.raise_for_status()
                results = resp.json()
                for r in results:
                    r_url = r.get("http_url_to_repo", "")
                    if repo_url.rstrip("/") in r_url or r_url.rstrip("/") in repo_url:
                        return r
                return None

    # ------------------------------------------------------------------
    # Webhook management
    # ------------------------------------------------------------------

    def list_webhooks(self, project_id: int) -> list[dict]:
        """GET /api/v4/projects/{id}/hooks -> list webhooks for a project."""
        url = f"{self._gitlab_url}/api/v4/projects/{project_id}/hooks"
        with httpx.Client() as client:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def create_webhook(
        self, project_id: int, url: str, secret_token: str = "",
    ) -> dict:
        """POST /api/v4/projects/{id}/hooks -> create a new webhook.

        Only subscribes to merge_request_events by default.
        """
        api_url = f"{self._gitlab_url}/api/v4/projects/{project_id}/hooks"
        payload = {
            "url": url,
            "push_events": False,
            "merge_requests_events": True,
            "note_events": False,
            "tag_push_events": False,
            "enable_ssl_verification": False,
        }
        if secret_token:
            payload["token"] = secret_token

        with httpx.Client() as client:
            resp = client.post(api_url, headers=self._get_headers(), json=payload)
            resp.raise_for_status()
            return resp.json()

    def delete_webhook(self, project_id: int, webhook_id: int) -> bool:
        """DELETE /api/v4/projects/{id}/hooks/{hook_id} -> delete a webhook."""
        url = f"{self._gitlab_url}/api/v4/projects/{project_id}/hooks/{webhook_id}"
        with httpx.Client() as client:
            resp = client.delete(url, headers=self._get_headers())
            resp.raise_for_status()
            return True

    def get_webhook_detail(self, project_id: int, webhook_id: int) -> dict:
        """GET /api/v4/projects/{id}/hooks/{hook_id} -> webhook details with health info."""
        url = f"{self._gitlab_url}/api/v4/projects/{project_id}/hooks/{webhook_id}"
        with httpx.Client() as client:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def list_webhook_deliveries(
        self, project_id: int, webhook_id: int, per_page: int = 5,
    ) -> list[dict]:
        """GET /api/v4/projects/{id}/hooks/{hook_id}/deliveries -> recent deliveries."""
        url = (
            f"{self._gitlab_url}/api/v4/projects/{project_id}"
            f"/hooks/{webhook_id}/deliveries"
            f"?per_page={per_page}"
        )
        with httpx.Client() as client:
            resp = client.get(url, headers=self._get_headers())
            resp.raise_for_status()
            return resp.json()

    def get_mr_diff_stats(self, repo_url: str, mr_id: int) -> list[dict]:
        """Get structured diff stats for each changed file in an MR.

        Returns list of:
          {"file_path": str, "old_path": str, "new_file": bool,
           "renamed_file": bool, "deleted_file": bool,
           "additions": int, "deletions": int}
        """
        changes = self.get_mr_changes(repo_url, mr_id)
        stats = []
        for c in changes.get("changes", []):
            diff = c.get("diff", "")
            additions = 0
            deletions = 0
            for line in diff.split("\n"):
                if line.startswith("+") and not line.startswith("+++"):
                    additions += 1
                elif line.startswith("-") and not line.startswith("---"):
                    deletions += 1
            stats.append({
                "file_path": c.get("new_path", ""),
                "old_path": c.get("old_path", ""),
                "new_file": c.get("new_file", False),
                "renamed_file": c.get("renamed_file", False),
                "deleted_file": c.get("deleted_file", False),
                "additions": additions,
                "deletions": deletions,
            })
        return stats

    def get_mr_raw_diffs(self, repo_url: str, mr_id: int) -> list[dict]:
        """Get raw diff content for each changed file in an MR.

        Returns list of:
          {"file_path": str, "diff": str, "new_file": bool,
           "deleted_file": bool, "renamed_file": bool}
        """
        changes = self.get_mr_changes(repo_url, mr_id)
        result = []
        for c in changes.get("changes", []):
            result.append({
                "file_path": c.get("new_path", ""),
                "old_path": c.get("old_path", ""),
                "diff": c.get("diff", ""),
                "new_file": c.get("new_file", False),
                "deleted_file": c.get("deleted_file", False),
                "renamed_file": c.get("renamed_file", False),
            })
        return result
