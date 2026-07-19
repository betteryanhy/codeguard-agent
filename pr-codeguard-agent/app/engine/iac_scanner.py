import json
import os
import sys
import shutil
import subprocess
import logging
from app.engine.base import AnalysisEngine
from app.models.finding import Finding

logger = logging.getLogger(__name__)


def _find_checkov() -> str | None:
    """Locate checkov executable, searching common locations."""
    logger.debug("Searching for checkov executable...")

    # 1. Try PATH (shutil.which resolves PATHEXT automatically)
    checkov_path = shutil.which("checkov")
    if checkov_path:
        logger.info("checkov found via PATH: %s", checkov_path)
        return checkov_path

    # 2. Try common pip user install paths
    user_scripts_dir = os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Python", "Python313", "Scripts")
    logger.debug("User scripts dir: %s", user_scripts_dir)

    # 2a. checkov.exe (most common)
    candidate = os.path.join(user_scripts_dir, "checkov.exe")
    logger.debug("Looking for checkov.exe: %s -> %s", candidate, os.path.isfile(candidate))
    if os.path.isfile(candidate):
        logger.info("checkov found: %s", candidate)
        return candidate

    # 2b. checkov.cmd (Windows batch wrapper)
    candidate = os.path.join(user_scripts_dir, "checkov.cmd")
    logger.debug("Looking for checkov.cmd: %s -> %s", candidate, os.path.isfile(candidate))
    if os.path.isfile(candidate):
        logger.info("checkov found: %s", candidate)
        return candidate

    # 2c. checkov (Python script with shebang, no extension)
    candidate = os.path.join(user_scripts_dir, "checkov")
    logger.debug("Looking for checkov (no ext): %s -> %s", candidate, os.path.isfile(candidate))
    if os.path.isfile(candidate):
        logger.info("checkov found: %s", candidate)
        return candidate

    # 3. Try conda/miniconda paths
    conda_prefix = os.environ.get("CONDA_PREFIX", "D:\\ProgramData\\miniconda3")
    logger.debug("Conda prefix: %s", conda_prefix)
    conda_candidates = [
        os.path.join(conda_prefix, "Scripts", "checkov.exe"),
        os.path.join(conda_prefix, "Scripts", "checkov.cmd"),
        os.path.join(conda_prefix, "Scripts", "checkov"),
        os.path.join(conda_prefix, "bin", "checkov"),
    ]
    for c in conda_candidates:
        exists = os.path.isfile(c)
        logger.debug("Looking for checkov in conda: %s -> %s", c, exists)
        if exists:
            logger.info("checkov found in conda: %s", c)
            return c

    logger.warning("checkov not found after searching all locations")
    return None


class IacScanner(AnalysisEngine):
    @property
    def name(self) -> str:
        return "iac"

    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        """Run Checkov IaC compliance scan on repository."""
        findings = []

        checkov_path = _find_checkov()
        if not checkov_path:
            logger.warning("Checkov not found. Install it with: pip install checkov")
            return findings

        # On Windows, run checkov via python -m to avoid .cmd/.exe PATH issues,
        # and set cwd=repo_path to work around cross-drive relpath failures.
        cmd = [
            sys.executable,
            "-m", "checkov.main",
            "--directory", repo_path,
            "--output", "json",
            "--quiet",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",  # Use UTF-8 instead of system default (cp936 on Chinese Windows)
                timeout=300,
                cwd=repo_path,  # Fix Windows cross-drive relpath issue
            )
            # Checkov return codes: 0=no issues, 1=issues found, 2=error
            if result.returncode <= 1 and result.stdout.strip():
                data = json.loads(result.stdout)
                # Checkov output format: results -> failed_checks
                failed_checks = data.get("results", {}).get("failed_checks", [])
                logger.info("IaC scan: %d failed checks found", len(failed_checks))
                for check in failed_checks:
                    findings.append(self._convert_finding(check))
            elif result.returncode == 2 and result.stderr:
                logger.warning("Checkov run reported errors:\n%s", result.stderr[:500])
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning("IaC scan failed (checkov may not be installed): %s", e)
        except Exception as e:
            logger.warning("IaC scan unexpected error: %s", e)

        return findings

    def _convert_finding(self, check: dict) -> Finding:
        severity_map = {"HIGH": "critical", "MEDIUM": "major", "LOW": "minor"}
        file_line_range = check.get("file_line_range", [])
        return Finding(
            engine=self.name,
            severity=severity_map.get(check.get("severity", "MEDIUM"), "major"),
            file_path=check.get("file_path", ""),
            line=file_line_range[0] if file_line_range else None,
            message=check.get("check_name", "IaC compliance issue"),
            code_snippet=str(check.get("code_block", ""))[:200],
            recommendation=check.get("guideline", "Fix the misconfiguration according to best practices"),
            rule_id=check.get("check_id", ""),
        )
