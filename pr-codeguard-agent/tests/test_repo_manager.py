import os
import tempfile
import pytest
from app.services.repo_manager import RepoManager


class TestRepoManager:
    def test_init_creates_base_dir(self):
        """Test that initialization creates the working directory."""
        manager = RepoManager()
        assert os.path.exists(manager.base_dir)

    def test_cleanup_nonexistent_dir(self):
        """Test cleanup doesn't raise on nonexistent path."""
        manager = RepoManager()
        manager.cleanup("/tmp/nonexistent_path_for_test_12345")  # should not raise

    def test_get_changed_files_no_repo(self):
        """Test get_changed_files returns empty list when git repo doesn't exist."""
        manager = RepoManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = manager.get_changed_files(tmpdir, "source", "target")
            assert result == []
