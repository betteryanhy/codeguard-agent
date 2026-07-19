import re
import os
from app.engine.base import AnalysisEngine
from app.models.finding import Finding


class BestPracticeScanner(AnalysisEngine):
    """Custom best practice and code quality scanner.
    
    Checks for common anti-patterns, commented secrets,
    missing configurations, and other code quality issues.
    Does NOT require external tools - pure Python regex checks.
    """

    @property
    def name(self) -> str:
        return "best_practice"

    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        findings = []

        if diff_files:
            # Only scan changed files
            for f in diff_files:
                full_path = os.path.join(repo_path, f.lstrip("/"))
                if os.path.isfile(full_path) and self._is_analyzable(f):
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as fh:
                            content = fh.read()
                        findings.extend(self._check_file(f, content))
                    except Exception:
                        pass
        else:
            # Scan all files
            for root, _, files in os.walk(repo_path):
                if ".git" in root:
                    continue
                for f in files:
                    relative_path = os.path.relpath(os.path.join(root, f), repo_path)
                    if self._is_analyzable(relative_path):
                        try:
                            with open(os.path.join(root, f), "r", encoding="utf-8", errors="ignore") as fh:
                                content = fh.read()
                            findings.extend(self._check_file(relative_path, content))
                        except Exception:
                            pass

        return findings

    def _is_analyzable(self, file_path: str) -> bool:
        text_extensions = {
            ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java",
            ".yaml", ".yml", ".tf", ".dockerfile", ".sh", ".bash",
            ".json", ".toml", ".ini", ".cfg", ".env", ".md",
        }
        ext = os.path.splitext(file_path)[1].lower()
        # Also check for Dockerfile (no extension)
        return ext in text_extensions or os.path.basename(file_path).lower() == "dockerfile"

    def _check_file(self, file_path: str, content: str) -> list[Finding]:
        findings = []
        lines = content.splitlines()

        for i, line in enumerate(lines, 1):
            stripped = line.strip()

            # Rule 1: Commented-out secrets
            if re.search(r'#\s*(API_KEY|SECRET|PASSWORD|TOKEN|PRIVATE_KEY)\s*=', stripped, re.IGNORECASE):
                findings.append(Finding(
                    engine=self.name,
                    severity="minor",
                    file_path=file_path,
                    line=i,
                    message="Commented-out secret/key found. Remove if not needed.",
                    code_snippet=stripped[:150],
                    recommendation="Remove commented-out sensitive information from code",
                ))

            # Rule 2: TODO without ticket reference
            if re.match(r'#\s*TODO[:\s]', stripped, re.IGNORECASE) and not re.search(r'[A-Z]+-\d+', stripped):
                findings.append(Finding(
                    engine=self.name,
                    severity="info",
                    file_path=file_path,
                    line=i,
                    message="TODO without ticket reference. Add JIRA/GitHub issue number.",
                    code_snippet=stripped[:150],
                    recommendation="Add ticket reference, e.g. # TODO(PROJ-123): description",
                ))

            # Rule 3: Print/debug statements in non-test files
            if file_path.endswith(".py") and "test_" not in file_path:
                if re.match(r'^\s*print\s*\(', stripped):
                    findings.append(Finding(
                        engine=self.name,
                        severity="info",
                        file_path=file_path,
                        line=i,
                        message="Debug print statement detected. Remove before production.",
                        code_snippet=stripped[:150],
                        recommendation="Replace print() with proper logging",
                    ))

            # Rule 4: Hardcoded localhost/port
            if re.search(r'localhost[:/]', stripped) or re.search(r'[:\s]3000\s*$', stripped):
                if file_path.endswith((".py", ".js", ".ts", ".sh", ".yaml", ".yml")):
                    findings.append(Finding(
                        engine=self.name,
                        severity="info",
                        file_path=file_path,
                        line=i,
                        message="Hardcoded localhost/port detected. Ensure this is intended for local dev.",
                        code_snippet=stripped[:150],
                        recommendation="Consider using environment variables for host/port configuration",
                    ))

        return findings
