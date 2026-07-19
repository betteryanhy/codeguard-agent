import json
import subprocess
from app.engine.base import AnalysisEngine
from app.models.finding import Finding


class SecretsScanner(AnalysisEngine):
    @property
    def name(self) -> str:
        return "secrets"

    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        """Run Gitleaks to detect hardcoded secrets."""
        findings = []
        cmd = ["gitleaks", "detect", "--source", repo_path, "--no-git", "-v"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                timeout=120,
            )
            for line in result.stdout.splitlines():
                try:
                    entry = json.loads(line)
                    findings.append(self._convert_finding(entry))
                except json.JSONDecodeError:
                    continue
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # gitleaks not installed or timed out - return empty
            pass
        except Exception:
            pass

        return findings

    def _convert_finding(self, entry: dict) -> Finding:
        severity_map = {"HIGH": "critical", "MEDIUM": "major", "LOW": "minor"}
        return Finding(
            engine=self.name,
            severity=severity_map.get(entry.get("Severity", ""), "minor"),
            file_path=entry.get("File", ""),
            line=entry.get("StartLine"),
            message=entry.get("Description", "Hardcoded secret detected"),
            code_snippet=entry.get("Secret", "")[:200],
            recommendation="Remove hardcoded secret and use environment variables or a secrets manager",
            rule_id=entry.get("RuleID", ""),
        )
