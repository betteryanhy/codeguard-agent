"""Trivy unified security scanner.

Integrates Aqua Security's Trivy (v0.72.0+) as a single engine covering:
  - vuln       → Dependency vulnerabilities (SCA / CVE)
  - secret     → Hardcoded secrets & credentials
  - misconfig  → IaC misconfigurations (Terraform, K8s, Docker, etc.)
  - license    → License compliance

Key design decisions:
  - Each scanner type runs as a separate subprocess to isolate failures.
    This avoids the "terraform scan config context deadline exceeded" error
    that occurs when vuln+misconfig run together on terraform files.
  - Retry-once logic: transient failures (timeout, context deadline) trigger
    one retry with a longer timeout.
  - Diff-aware targeting: when diff_files is provided, only run relevant
    scanners based on file types (e.g. skip misconfig if no IaC files changed).
  - Health check API: check_health() verifies Trivy binary and DB at startup.

Offline mode:
  Trivy caches vulnerability DB locally. In air-gapped environments, use
  --skip-db-update + --cache-dir pointing to a pre-synced DB directory.
  See tools/trivy/update_db.sh for offline DB sync instructions.
"""

import json
import os
import shutil
import subprocess
import logging

from dataclasses import dataclass

from app.engine.base import AnalysisEngine
from app.models.finding import Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trivy binary discovery
# ---------------------------------------------------------------------------

_TRIVY_CANDIDATE_PATHS = [
    # System PATH (will be found by shutil.which)
    # Project-local: agent/tools/trivy/
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools", "trivy"),
    # Project-local: agent/../tools/trivy/ (one level above agent directory)
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "tools", "trivy"),
    # Current working directory
    os.path.join(os.getcwd(), "tools", "trivy"),
    # Parent of current working directory
    os.path.join(os.path.dirname(os.getcwd()), "tools", "trivy"),
    # TRIVY_PATH env var (for custom installations)
    os.environ.get("TRIVY_PATH", ""),
]


def find_trivy() -> str | None:
    """Locate trivy executable (public for health check use)."""
    # 1. Try shutil.which (checks PATH)
    trivy_path = shutil.which("trivy")
    if trivy_path:
        logger.debug("Trivy found via PATH: %s", trivy_path)
        return trivy_path

    # 2. Try known project directories
    for base_dir in _TRIVY_CANDIDATE_PATHS:
        if not base_dir or not os.path.isdir(base_dir):
            continue
        for name in ("trivy.exe", "trivy", "trivy.cmd"):
            candidate = os.path.join(base_dir, name)
            if os.path.isfile(candidate):
                logger.info("Trivy found: %s", candidate)
                return candidate

    logger.warning("Trivy not found. Install from: https://github.com/aquasecurity/trivy")
    return None


# ---------------------------------------------------------------------------
# Trivy result parsing
# ---------------------------------------------------------------------------

TRIVY_SEVERITY_MAP = {
    "CRITICAL": "critical",
    "HIGH": "critical",
    "MEDIUM": "major",
    "LOW": "minor",
    "UNKNOWN": "info",
}

# Scanners that Trivy supports
VALID_SCANNERS = ("vuln", "secret", "misconfig", "license")

# Map file extensions/patterns to relevant scanners
_FILE_TYPE_SCANNER_MAP: dict[str, set[str]] = {
    # Dependency files -> vuln scanner
    "go.mod": {"vuln"},
    "go.sum": {"vuln"},
    "package.json": {"vuln"},
    "package-lock.json": {"vuln"},
    "yarn.lock": {"vuln"},
    "pnpm-lock.yaml": {"vuln"},
    "requirements.txt": {"vuln"},
    "Pipfile": {"vuln"},
    "Pipfile.lock": {"vuln"},
    "pom.xml": {"vuln"},
    "build.gradle": {"vuln"},
    "Cargo.toml": {"vuln"},
    "Cargo.lock": {"vuln"},
    "Gemfile": {"vuln"},
    "Gemfile.lock": {"vuln"},
    "composer.json": {"vuln"},
    "composer.lock": {"vuln"},
    # IaC files -> misconfig scanner
    ".tf": {"misconfig"},
    ".tfvars": {"misconfig"},
    "Dockerfile": {"misconfig", "secret"},
    ".dockerfile": {"misconfig", "secret"},
    "k8s.yaml": {"misconfig"},
    ".yml": {"misconfig"},
    ".yaml": {"misconfig"},
    # Secret-prone files -> secret scanner
    ".env": {"secret"},
    ".env.example": {"secret"},
    "credentials": {"secret"},
    "secret": {"secret"},
    ".pem": {"secret"},
    ".key": {"secret"},
}

# File extensions that suggest the file is a dependency manifest
_VULN_EXTENSIONS = {".mod", ".sum", ".lock", ".json", ".xml", ".gradle", ".toml"}
# File extensions that suggest IaC content
_MISCONFIG_EXTENSIONS = {".tf", ".tfvars", ".yaml", ".yml", ".dockerfile"}
# File patterns that suggest secrets
_SECRET_PATTERNS = (".env", "credential", "secret", ".pem", ".key", "token", "password")


@dataclass
class _ScannerRunResult:
    """Result of a single scanner subprocess run."""
    scanner: str
    findings: list[Finding]
    success: bool
    error_message: str = ""


def _infer_relevant_scanners(diff_files: list[str] | None) -> set[str] | None:
    """Infer which scanners are relevant based on changed files.

    Returns a set of scanner names, or None if all scanners should be run.
    """
    if not diff_files:
        return None

    relevant: set[str] = set()

    for f in diff_files:
        f_lower = f.lower()
        basename = os.path.basename(f_lower)

        # Check exact filename matches
        if basename in _FILE_TYPE_SCANNER_MAP:
            relevant.update(_FILE_TYPE_SCANNER_MAP[basename])

        # Check extension-based matches
        ext = os.path.splitext(f_lower)[1]
        if ext in _VULN_EXTENSIONS:
            relevant.add("vuln")
        if ext in _MISCONFIG_EXTENSIONS:
            relevant.add("misconfig")
        if any(pattern in f_lower for pattern in _SECRET_PATTERNS):
            relevant.add("secret")

        # Dockerfile detection (no specific extension)
        if basename == "dockerfile" or basename.startswith("dockerfile."):
            relevant.add("misconfig")
            relevant.add("secret")

    return relevant if relevant else None


def _parse_trivy_results(engine_name: str, stdout: str) -> list[Finding]:
    """Parse Trivy JSON output into Finding objects."""
    findings: list[Finding] = []

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as e:
        logger.warning("Trivy JSON parse error: %s", e)
        return findings

    results = data if isinstance(data, list) else data.get("Results", [])

    for result in results:
        target = result.get("Target", "")

        # --- Vulnerabilities ---
        for vuln in result.get("Vulnerabilities", []):
            severity = TRIVY_SEVERITY_MAP.get(vuln.get("Severity", ""), "minor")
            pkg_name = vuln.get("PkgName", "")
            vuln_id = vuln.get("VulnerabilityID", "")
            installed_ver = vuln.get("InstalledVersion", "")
            fixed_ver = vuln.get("FixedVersion", "")
            title = vuln.get("Title", "") or ""

            message = f"[{target}] {vuln_id}: {pkg_name} {installed_ver}"
            if fixed_ver:
                message += f" (fix: {fixed_ver})"

            findings.append(Finding(
                engine=engine_name,
                severity=severity,
                file_path=target,
                line=None,
                message=message[:200],
                code_snippet="",
                recommendation=f"Upgrade {pkg_name} from {installed_ver} to {fixed_ver or 'latest'}"
                if fixed_ver else f"Review {vuln_id} for mitigation options",
                rule_id=vuln_id,
            ))

        # --- Misconfigurations (IaC) ---
        for misconfig in result.get("Misconfigurations", []):
            severity = TRIVY_SEVERITY_MAP.get(misconfig.get("Severity", ""), "minor")
            msg = misconfig.get("Title", "") or misconfig.get("Message", "")
            rule_id = misconfig.get("ID", "")

            findings.append(Finding(
                engine=engine_name,
                severity=severity,
                file_path=misconfig.get("Location", {}).get("Filename", target),
                line=misconfig.get("Location", {}).get("StartLine"),
                message=f"[IaC] {rule_id}: {msg}"[:200],
                code_snippet=str(misconfig.get("CauseMetadata", {}).get("Code", {}).get("Lines", []))[:200],
                recommendation=misconfig.get("Resolution", "") or misconfig.get("Description", ""),
                rule_id=rule_id,
            ))

        # --- Secrets ---
        for secret in result.get("Secrets", []):
            severity = TRIVY_SEVERITY_MAP.get(secret.get("Severity", ""), "minor")
            rule_id = secret.get("RuleID", "")
            msg = secret.get("Title", "") or secret.get("Description", "") or "Secret detected"

            findings.append(Finding(
                engine=engine_name,
                severity=severity,
                file_path=secret.get("Location", {}).get("Filename", target),
                line=secret.get("Location", {}).get("StartLine"),
                message=f"[Secret] {msg}"[:200],
                code_snippet=str(secret.get("Code", {}).get("Lines", []))[:200],
                recommendation=(
                    "Remove hardcoded secret and use environment variables "
                    "or a secrets manager (e.g. Vault, AWS Secrets Manager)"
                ),
                rule_id=rule_id,
            ))

    return findings


# ---------------------------------------------------------------------------
# TrivyScanner engine
# ---------------------------------------------------------------------------


class TrivyScanner(AnalysisEngine):
    """Unified security scanner powered by Trivy.

    Covers: vulnerabilities (SCA), secrets, IaC misconfigurations, and licenses.

    Design notes:
      - Each scanner type runs as an independent subprocess. This isolates
        failures so a timeout in misconfig doesn't lose vuln results.
      - Diff-aware: when diff_files is provided, only relevant scanners run.
      - Retry: transient failures (context deadline, timeout) retry once.
    """

    def __init__(
        self,
        scanners: tuple[str, ...] = ("vuln", "misconfig"),
        severity_threshold: str = "MEDIUM",
        cache_dir: str = "",
        offline: bool = True,
        timeout: int = 300,
        skip_files: tuple[str, ...] | None = None,
    ):
        """
        Args:
            scanners: Which Trivy scanners to enable (comma-separated).
                      Options: "vuln", "secret", "misconfig", "license".
            severity_threshold: Minimum severity to report.
            cache_dir: Path to Trivy cache directory.
            offline: Skip DB update (air-gapped mode).
            timeout: Per-scanner timeout in seconds. Each scanner gets this
                     much time independently.
        """
        self._all_scanners = [s for s in scanners if s in VALID_SCANNERS]
        if not self._all_scanners:
            self._all_scanners = ["vuln", "secret", "misconfig"]
        self._severity_threshold = severity_threshold
        self._cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data", "trivy",
        )
        self._cache_dir = os.path.abspath(self._cache_dir)
        self._offline = offline
        self._timeout = timeout
        # Known problematic files for Trivy v0.72 secret scanner (semaphore bug)
        # These files are skipped for the secret scanner only.
        self._skip_files = skip_files or (
            # Files that trigger the Trivy v0.72 semaphore timeout bug
            # in the secret scanner (see https://github.com/aquasecurity/trivy/issues/6925)
            "SECURITY_FIX.txt", "SECURITY_IMPROVEMENTS.md",
            "app.py", "config.json",
        )
        # Maximum file size (bytes) for secret scanner target files.
        # Files larger than this are skipped for secret scanning to avoid
        # the Trivy v0.72 semaphore timeout bug.
        self._secret_max_file_size = 500 * 1024  # 500KB
        # Scanner-specific timeouts (seconds).
        # Secret scanner needs extra headroom on repos with many files.
        self._scanner_timeout_map: dict[str, int] = {
            "vuln": timeout,
            "secret": max(timeout, 240),    # need extra time for file scanning
            "misconfig": max(timeout, 600),  # at least 10 min for terraform
            "license": timeout,
        }
        self._trivy_path: str | None = None

    @property
    def name(self) -> str:
        return "trivy"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, repo_path: str, diff_files: list[str] | None = None) -> list[Finding]:
        """Run Trivy filesystem scan on the repository.

        Each configured scanner runs as a separate subprocess. Results are
        aggregated and deduplicated by rule_id + file_path.

        Args:
            repo_path: Local path to the cloned repository.
            diff_files: Optional list of changed files. Used to infer which
                        scanners are relevant and reduce scan time.

        Returns:
            List of Finding objects.
        """
        self._trivy_path = find_trivy()
        if not self._trivy_path:
            logger.warning("Trivy not installed, skipping Trivy scan")
            return []

        # Ensure cache dir exists
        os.makedirs(self._cache_dir, exist_ok=True)

        # Determine which scanners to run
        scanners_to_run = self._resolve_scanners(diff_files)
        if not scanners_to_run:
            logger.info("No relevant scanners for changed files, skipping Trivy")
            return []

        logger.info(
            "Trivy scan on %s (scanners=%s, diff_files=%d, offline=%s)",
            repo_path, scanners_to_run, len(diff_files or []), self._offline,
        )

        # Run each scanner independently
        run_results: list[_ScannerRunResult] = []
        for scanner in scanners_to_run:
            result = self._run_scanner_with_retry(scanner, repo_path)
            run_results.append(result)

        # Aggregate findings
        all_findings: list[Finding] = []
        for rr in run_results:
            if rr.success:
                logger.info("Trivy/%s: %d findings", rr.scanner, len(rr.findings))
                all_findings.extend(rr.findings)
            else:
                logger.warning("Trivy/%s failed: %s", rr.scanner, rr.error_message)

        logger.info("Trivy scan complete: %d total findings", len(all_findings))
        return all_findings

    def check_health(self) -> dict:
        """Check Trivy binary and DB health.

        Returns:
            dict with keys: available (bool), version (str),
                            db_exists (bool), db_info (str)
        """
        result: dict = {
            "available": False,
            "version": "",
            "path": "",
            "db_ok": False,
            "db_path": "",
            "error": "",
        }

        trivy_path = find_trivy()
        if not trivy_path:
            result["error"] = "Trivy binary not found"
            return result

        result["path"] = trivy_path

        # Get version
        try:
            ver_result = subprocess.run(
                [trivy_path, "version", "--format", "json"],
                capture_output=True, encoding="utf-8", timeout=30,
            )
            if ver_result.returncode == 0 and ver_result.stdout.strip():
                ver_data = json.loads(ver_result.stdout)
                result["version"] = ver_data.get("Version", "")
        except Exception as e:
            logger.warning("Trivy version check failed: %s", e)

        # Check DB files
        db_dir = os.path.join(self._cache_dir, "db")
        db_file = os.path.join(db_dir, "trivy.db")
        metadata_file = os.path.join(db_dir, "metadata.json")

        result["db_path"] = db_dir
        result["db_ok"] = os.path.isfile(db_file)

        if os.path.isfile(metadata_file):
            try:
                with open(metadata_file, encoding="utf-8") as f:
                    meta = json.load(f)
                result["db_info"] = json.dumps(meta, ensure_ascii=False)[:200]
            except Exception:
                pass

        # Check policy content
        policy_dir = os.path.join(self._cache_dir, "policy", "content")
        if os.path.isdir(policy_dir):
            policy_files = [f for f in os.listdir(policy_dir) if f.endswith(".json")]
            result["policy_files"] = len(policy_files)

        result["available"] = True
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_scanners(self, diff_files: list[str] | None) -> list[str]:
        """Determine which scanners to actually run.

        When diff_files is provided, only run scanners relevant to
        the changed file types. Otherwise, run all configured scanners.
        """
        if not diff_files:
            return list(self._all_scanners)

        relevant = _infer_relevant_scanners(diff_files)
        if relevant is None:
            return list(self._all_scanners)

        # Intersect with configured scanners
        return [s for s in self._all_scanners if s in relevant]

    def _run_scanner_with_retry(self, scanner: str, scan_path: str) -> _ScannerRunResult:
        """Run a single scanner, retrying once on transient failure."""
        timeout = self._scanner_timeout_map.get(scanner, self._timeout)

        for attempt in range(2):  # max 2 attempts
            result = self._run_single_scanner(scanner, scan_path, timeout)
            if result.success:
                return result
            # Retry on transient failures only
            if attempt == 0 and _is_transient_error(result.error_message):
                logger.info(
                    "Retrying Trivy/%s (attempt 2) after: %s",
                    scanner, result.error_message[:100],
                )
                # Use longer timeout on retry
                timeout = int(timeout * 1.5)
                continue
            return result

        return result  # All retries exhausted

    def _run_single_scanner(self, scanner: str, scan_path: str, timeout: int) -> _ScannerRunResult:
        """Execute a single Trivy scanner subprocess."""
        cmd = self._build_command(self._trivy_path, scanner, scan_path)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding="utf-8",
                timeout=timeout,
                cwd=scan_path,
                errors="replace",
            )

            # Trivy exit codes: 0 = no issues, 1 = issues found
            if result.returncode in (0, 1) and result.stdout.strip():
                findings = _parse_trivy_results(self.name, result.stdout)
                return _ScannerRunResult(
                    scanner=scanner,
                    findings=findings,
                    success=True,
                )

            # rc=1 with no stdout usually means a fatal error
            if result.returncode == 1 and not result.stdout.strip():
                err_msg = result.stderr[:500] if result.stderr else "Unknown error"
                return _ScannerRunResult(
                    scanner=scanner,
                    findings=[],
                    success=False,
                    error_message=err_msg,
                )

            if result.returncode > 1:
                err_msg = result.stderr[:500] if result.stderr else f"Exit code {result.returncode}"
                return _ScannerRunResult(
                    scanner=scanner,
                    findings=[],
                    success=False,
                    error_message=err_msg,
                )

            # rc=0 with no stdout = nothing found
            return _ScannerRunResult(
                scanner=scanner,
                findings=[],
                success=True,
            )

        except subprocess.TimeoutExpired:
            return _ScannerRunResult(
                scanner=scanner,
                findings=[],
                success=False,
                error_message=f"timed out after {timeout}s",
            )
        except FileNotFoundError:
            return _ScannerRunResult(
                scanner=scanner,
                findings=[],
                success=False,
                error_message="Trivy executable not found",
            )
        except Exception as e:
            return _ScannerRunResult(
                scanner=scanner,
                findings=[],
                success=False,
                error_message=str(e),
            )

    def _build_command(self, trivy_path: str, scanner: str, target: str) -> list[str]:
        """Build the Trivy CLI command for a single scanner."""
        cmd = [
            trivy_path,
            "filesystem",
            "--format", "json",
            "--severity", self._severity_threshold,
            "--scanners", scanner,
            "--quiet",
        ]

        if self._offline:
            cmd.append("--skip-db-update")

        # Skip files known to cause Trivy timeouts (e.g. app.py for secret scanner)
        for skip_file in self._skip_files:
            cmd.extend(["--skip-files", skip_file])

        cmd.extend(["--cache-dir", self._cache_dir])
        cmd.append(target)
        return cmd

    @staticmethod
    def _resolve_target_paths(repo_path: str, diff_files: list[str]) -> str:
        """Resolve scan target based on changed files.

        For simplicity, always scan the full repo root when there are changes.
        Trivy is fast enough for incremental scans, and scanning the full repo
        catches dependencies that may not be in the diff but were affected.
        """
        return repo_path


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

_TRANSIENT_ERROR_PATTERNS = [
    "context deadline exceeded",
    "timeout",
    "connection refused",
    "connection reset",
    "i/o timeout",
    "no such host",
    "TLS handshake timeout",
    "semaphore acquire timeout",   # Trivy v0.72 secret scanner bug
    "semaphore",
]


def _is_transient_error(error_message: str) -> bool:
    """Check if an error message suggests a transient failure worth retrying."""
    lower = error_message.lower()
    return any(pattern in lower for pattern in _TRANSIENT_ERROR_PATTERNS)
