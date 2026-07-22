import os
import shutil
import stat
from urllib.parse import urlparse, urlunparse
from git import Repo
from git.exc import InvalidGitRepositoryError, NoSuchPathError
from app.config import settings


def _remove_readonly(func, path, _):
    """Clear read-only bit and retry removal (Windows workaround)."""
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _rmtree(path: str):
    """Remove a directory tree, handling Windows read-only files."""
    if os.path.exists(path):
        shutil.rmtree(path, onerror=_remove_readonly)


class RepoManager:
    """Manage local repository cloning and cleanup for scanning."""

    def __init__(self):
        self.base_dir = settings.work_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _inject_auth(self, repo_url: str) -> str:
        """Inject GitLab API token into HTTP(S) repo URLs for authentication."""
        if not settings.gitlab_api_token:
            return repo_url
        parsed = urlparse(repo_url)
        if parsed.scheme in ("http", "https") and not parsed.username:
            # Replace Docker-internal hostnames with 127.0.0.1:8081
            netloc = parsed.netloc.replace("localhost", "127.0.0.1")
            if netloc == "gitlab":
                netloc = "127.0.0.1:8081"
            elif netloc.startswith("gitlab:"):
                netloc = netloc.replace("gitlab:", "127.0.0.1:", 1)
            # Inject oauth2:token as credentials
            netloc = f"oauth2:{settings.gitlab_api_token}@{netloc}"
            parsed = parsed._replace(netloc=netloc)
            return urlunparse(parsed)
        return repo_url

    def clone_repo(self, repo_url: str, branch: str, mr_id: int) -> str:
        """
        Clone repository to temp directory and checkout branch.
        
        Args:
            repo_url: Git repository URL (http/https)
            branch: Branch name to checkout
            mr_id: MR ID for directory naming
            
        Returns:
            str: Local path to cloned repository
            
        Raises:
            git.exc.GitCommandError: If clone fails
        """
        # Create a safe directory name from repo URL
        safe_name = repo_url.replace("://", "_").replace("/", "_").replace(".", "_").replace(":", "_")
        clone_dir = os.path.join(self.base_dir, f"{safe_name}_mr{mr_id}")

        # Clean up if exists
        if os.path.exists(clone_dir):
            _rmtree(clone_dir)

        # Full clone (depth=1 causes Windows lock file issues)
        auth_url = self._inject_auth(repo_url)
        Repo.clone_from(auth_url, clone_dir, branch=branch, depth=None)
        return clone_dir

    def cleanup(self, clone_dir: str):
        """Remove cloned repository directory safely."""
        if clone_dir and os.path.exists(clone_dir):
            _rmtree(clone_dir)

    def get_changed_files(self, repo_path: str, source_branch: str, target_branch: str) -> list[str]:
        """
        Get list of changed files between two branches.
        Uses git diff to find modified files.
        
        Args:
            repo_path: Local path to cloned repo
            source_branch: Source branch name
            target_branch: Target branch name
            
        Returns:
            list[str]: List of file paths that changed
        """
        try:
            repo = Repo(repo_path)
            diff = repo.git.diff(f"origin/{target_branch}...origin/{source_branch}", name_only=True)
            if diff.strip():
                return [f.strip() for f in diff.split("\n") if f.strip()]
            return []
        except (InvalidGitRepositoryError, NoSuchPathError):
            return []
