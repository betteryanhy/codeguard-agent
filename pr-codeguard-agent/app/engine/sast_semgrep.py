"""Semgrep SAST engine for static code analysis.

Integrates Semgrep CLI (>=1.0.0) to detect:
  - SQL injection
  - Path traversal
  - Hardcoded secrets
  - Dangerous function usage (eval, exec, os.system)
  - Debug information leaks

Uses Semgrep Registry rules (--config auto) and supports custom rules.
Each scan runs as a subprocess with configurable timeout and file filtering.
"""

import json
import logging
import os
import shutil
import subprocess

from app.engine.base import AnalysisEngine
from app.models.finding import Finding

logger = logging.getLogger(__name__)

# Mapping from Semgrep severity to CodeGuard severity
SEVERITY_MAP = {
    "ERROR": "critical",
    "WARNING": "major",
    "INFO": "minor",
    "INVENTORY": "info",
}

# Language extensions Semgrep can analyze
SUPPORTED_EXTENSIONS = {
    ".py", ".go", ".java", ".js", ".ts", ".jsx", ".tsx",
    ".rb", ".php", ".c", ".cpp", ".h", ".hpp",
    ".cs", ".swift", ".kt", ".scala", ".rs",
    ".tf", ".yaml", ".yml", ".json", ".xml",
    ".sql", ".sh", ".bash", ".zsh",
}


class SemgrepScanner(AnalysisEngine):
    """SAST scanner powered by Semgrep.

    Covers: SQL injection, path traversal, hardcoded secrets,
            dangerous functions, and debug leaks.
    """

    def __init__(
        self,
        timeout: int = 300,
        max_target_bytes: int = 500_000,
        config: str = "auto",
    ):
        """
        Args:
            timeout: Per-scan timeout in seconds.
            max_target_bytes: Skip files larger than this (bytes).
            config: Semgrep config source ("auto" for registry rules,
                    or path to custom rule file).
        """
        self._timeout = timeout
        self._max_target_bytes = max_target_bytes
        self._config = config

    @property
    def name(self) -> str:
        return "sast_semgrep"

    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        """Run Semgrep scan on the repository.

        Args:
            repo_path: Local path to the cloned repository.
            diff_files: Optional list of changed files. When provided,
                       only these files are scanned.

        Returns:
            List of Finding objects.
        """
        semgrep_path = self._find_semgrep()
        if not semgrep_path:
            logger.warning("Semgrep not found, skipping SAST scan")
            return []

        # Determine scan targets
        targets = self._resolve_targets(repo_path, diff_files)
        if not targets:
            logger.info("No relevant files for Semgrep scan, skipping")
            return []

        cmd = self._build_command(semgrep_path, targets)

        logger.info(
            "Semgrep scan on %s (%d targets, config=%s, timeout=%ds)",
            repo_path, len(targets), self._config, self._timeout,
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                timeout=self._timeout,
                errors="replace",
            )

            findings = self._parse_results(result.stdout, repo_path)
            logger.info("Semgrep scan complete: %d findings", len(findings))
            return findings

        except subprocess.TimeoutExpired:
            logger.error("Semgrep scan timed out after %ds", self._timeout)
            return []
        except FileNotFoundError:
            logger.error("Semgrep executable not found")
            return []
        except Exception as e:
            logger.error("Semgrep scan failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_semgrep(self) -> str | None:
        """Locate the semgrep executable."""
        # 1. Try PATH
        semgrep_path = shutil.which("semgrep")
        if semgrep_path:
            return semgrep_path

        # 2. Try project-local
        local_paths = [
            os.path.join(os.getcwd(), "tools", "semgrep", "semgrep.exe"),
            os.path.join(os.getcwd(), "tools", "semgrep", "semgrep"),
            os.path.join(os.path.dirname(os.getcwd()), "tools", "semgrep", "semgrep.exe"),
        ]
        for path in local_paths:
            if os.path.isfile(path):
                return path

        # 3. Try python -m semgrep
        try:
            result = subprocess.run(
                ["python", "-m", "semgrep", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                logger.info("Semgrep found via python -m semgrep: %s", result.stdout.strip())
                return "python -m semgrep"
        except Exception:
            pass

        return None

    def _resolve_targets(self, repo_path: str, diff_files: list[str] | None) -> list[str]:
        """Resolve which files to scan.

        When diff_files is provided, only scan changed files that have
        supported extensions. Otherwise, scan the whole repo.
        """
        if not diff_files:
            return [repo_path]

        targets = []
        for f in diff_files:
            ext = os.path.splitext(f.lower())[1]
            if ext in SUPPORTED_EXTENSIONS:
                full_path = os.path.join(repo_path, f)
                if os.path.isfile(full_path):
                    # Check file size
                    try:
                        if os.path.getsize(full_path) <= self._max_target_bytes:
                            targets.append(full_path)
                    except OSError:
                        continue

        return targets

    def _build_command(self, semgrep_path: str, targets: list[str]) -> list[str]:
        """Build the Semgrep CLI command."""
        cmd = (
            semgrep_path.split()
            if " " in semgrep_path
            else [semgrep_path]
        )
        cmd.extend([
            "scan",
            "--json",
            "--no-rewrite-rule-ids",
            "--quiet",
            "--config", self._config,
            "--severity", "ERROR,WARNING",
            "--max-target-bytes", str(self._max_target_bytes),
            "--max-memory", "512",
            "--timeout", "30",
        ])
        cmd.extend(targets)
        return cmd

    def _parse_results(self, stdout: str, repo_path: str) -> list[Finding]:
        """Parse Semgrep JSON output into Finding objects.

        Semgrep JSON format:
        {
            "results": [{
                "check_id": "rules.sql-injection",
                "path": "/abs/path/to/file.py",
                "start": {"line": 42, "col": 5},
                "end": {"line": 42, "col": 80},
                "extra": {
                    "severity": "ERROR",
                    "message": "Found SQL injection...",
                    "lines": "cursor.execute(f\"SELECT * FROM users WHERE id = {user_input}\")",
                    "metadata": {"cwe": "CWE-89"},
                    "fix": "Use parameterized queries",
                }
            }]
        }
        """
        findings = []

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            logger.warning("Semgrep JSON parse error: %s", e)
            return findings

        for result in data.get("results", []):
            path = result.get("path", "")
            extra = result.get("extra", {})
            start = result.get("start", {})

            # Make path relative to repo
            rel_path = path
            if repo_path and path.startswith(repo_path):
                rel_path = os.path.relpath(path, repo_path)

            severity = SEVERITY_MAP.get(
                extra.get("severity", ""), "major"
            )
            message = extra.get("message", "")
            lines = extra.get("lines", "")
            check_id = result.get("check_id", "")
            fix = extra.get("fix", "")

            # Extract CWE from metadata
            metadata = extra.get("metadata", {})
            cwe = metadata.get("cwe", "")
            if isinstance(cwe, list):
                cwe = ", ".join(cwe)

            # Build recommendation
            recommendation = fix or ""
            if cwe and not recommendation:
                recommendation = f"Refer to {cwe} for mitigation"

            findings.append(Finding(
                engine="sast_semgrep",
                severity=severity,
                file_path=rel_path,
                line=start.get("line"),
                message=message[:200],
                code_snippet=lines[:200] if lines else "",
                recommendation=recommendation[:200],
                rule_id=check_id,
            ))

        # Deduplicate by (rule_id, file_path, line)
        return self._deduplicate(findings)

    @staticmethod
    def _deduplicate(findings: list[Finding]) -> list[Finding]:
        """Remove duplicate findings with the same rule_id + file_path + line."""
        seen: set[tuple] = set()
        unique: list[Finding] = []
        for f in findings:
            key = (f.rule_id, f.file_path, f.line)
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique
