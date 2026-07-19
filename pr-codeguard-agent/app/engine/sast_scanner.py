import json
import subprocess
import os
from app.engine.base import AnalysisEngine
from app.models.finding import Finding


class SastScanner(AnalysisEngine):
    @property
    def name(self) -> str:
        return "sast"

    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        """Run Semgrep SAST scan on repository."""
        findings = []

        # Find semgrep rules directory (relative to project root)
        rules_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "rules", "semgrep")
        rules_dir = os.path.abspath(rules_dir)

        if not os.path.exists(rules_dir):
            return findings  # No rules to run

        cmd = [
            "semgrep",
            "--config", rules_dir,
            "--json",
            "--quiet",
            "--no-git-ignore",
            repo_path,
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                timeout=180,
            )
            # Semgrep returns 0 if no findings, 1 if findings found
            if result.returncode in (0, 1) and result.stdout.strip():
                data = json.loads(result.stdout)
                for r in data.get("results", []):
                    findings.append(self._convert_finding(r))
        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
            pass
        except Exception:
            pass

        return findings

    def _convert_finding(self, result: dict) -> Finding:
        severity_map = {"ERROR": "critical", "WARNING": "major", "INFO": "minor"}
        extra = result.get("extra", {})
        return Finding(
            engine=self.name,
            severity=severity_map.get(extra.get("severity", "INFO"), "minor"),
            file_path=result.get("path", ""),
            line=result.get("start", {}).get("line"),
            message=extra.get("message", "Security issue detected"),
            code_snippet=(extra.get("lines") or "")[:200],
            recommendation="",
            rule_id=result.get("check_id", ""),
        )
