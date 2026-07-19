from app.services.gitlab_client import GitLabClient


class TestGitLabClient:
    def test_extract_project_path_with_git_suffix(self):
        path = GitLabClient._extract_project_path("http://gitlab/root/my-project.git")
        assert path == "root/my-project"

    def test_extract_project_path_without_git(self):
        path = GitLabClient._extract_project_path("http://gitlab/root/my-project")
        assert path == "root/my-project"

    def test_extract_project_path_namespace(self):
        path = GitLabClient._extract_project_path(
            "http://gitlab/group/subgroup/project.git"
        )
        assert path == "group/subgroup/project"

    def test_extract_project_path_with_http(self):
        path = GitLabClient._extract_project_path(
            "http://gitlab.local:8080/namespace/project.git"
        )
        assert path == "namespace/project"

    def test_extract_project_path_root_group(self):
        path = GitLabClient._extract_project_path("http://gitlab/root/project.git")
        assert path == "root/project"
