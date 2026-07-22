import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.models.task import ScanTask
from app.models.finding import Finding
from app.services.repo_manager import RepoManager

logger = logging.getLogger(__name__)


class Orchestrator:
    """Orchestrates the scan pipeline: clone → run engines → collect findings."""

    def __init__(self):
        self.repo_manager = RepoManager()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._engines: dict[str, "AnalysisEngine"] = {}
        self._ai_engine: "AIReviewEngine | None" = None
        self._init_engines()

    def _init_engines(self):
        """Initialize enabled engines based on config."""
        from app.engine.secrets_scanner import SecretsScanner
        from app.engine.sast_scanner import SastScanner
        from app.engine.iac_scanner import IacScanner
        from app.engine.best_practice import BestPracticeScanner
        from app.engine.trivy_scanner import TrivyScanner
        from app.engine.sast_semgrep import SemgrepScanner

        engine_configs = [
            ("secrets", SecretsScanner, settings.engines_secrets_enabled),
            ("sast", SastScanner, settings.engines_sast_enabled),
            ("iac", IacScanner, settings.engines_iac_enabled),
            ("best_practice", BestPracticeScanner, settings.engines_best_practice_enabled),
            ("trivy", TrivyScanner, settings.engines_trivy_enabled),
            ("sast_semgrep", SemgrepScanner, settings.engines_sast_semgrep_enabled),
        ]

        for name, cls, enabled in engine_configs:
            if enabled:
                if name == "trivy":
                    kwargs = dict(
                        scanners=tuple(settings.trivy_scanners.split(",")),
                        severity_threshold=settings.trivy_severity_threshold,
                        cache_dir=settings.trivy_cache_dir,
                        offline=settings.trivy_offline,
                        timeout=settings.trivy_timeout,
                    )
                    self._engines[name] = cls(**kwargs)
                else:
                    self._engines[name] = cls()
                logger.info(f"Engine '{name}' initialized")

        # Initialize AI engine if enabled
        if settings.ai_enabled:
            from app.engine.ai_review import AIReviewEngine
            self._ai_engine = AIReviewEngine()
            logger.info("AI Review Engine initialized")

    @property
    def enabled_engines(self) -> list[str]:
        engines = list(self._engines.keys())
        if self._ai_engine:
            engines.append("ai_review")
        return engines

    async def run_scan(
        self,
        task: ScanTask,
        source_branch: str,
        target_branch: str,
        diff_files: list[str] | None = None,
        enabled_engines: list[str] | None = None,
        ai_enabled: bool | None = None,
        tf_change_detection: bool = True,
    ) -> ScanTask:
        """
        Run the complete scan pipeline for a task.

        Args:
            task: ScanTask object with id, repo_url, mr_id
            source_branch: MR source branch
            target_branch: MR target branch
            diff_files: Optional list of changed file paths
            enabled_engines: Optional list of engine names to run.
                             If None, runs all initialized engines.
            ai_enabled: Whether to run AI enrichment. If None, uses config default.
            tf_change_detection: Whether to run Terraform change analysis.

        Returns:
            ScanTask with findings populated
        """
        clone_dir = None
        try:
            logger.info(f"[{task.id}] Cloning repo: {task.repo_url} branch={source_branch}")
            clone_dir = self.repo_manager.clone_repo(task.repo_url, source_branch, task.mr_id)

            # If no diff_files provided, try to get them from git
            if not diff_files:
                diff_files = self.repo_manager.get_changed_files(clone_dir, source_branch, target_branch)

            task.status = "running"
            loop = asyncio.get_event_loop()
            all_findings: list[Finding] = []

            # Run all engines concurrently (filter by enabled_engines if provided)
            engine_tasks = []
            for engine_name, engine in self._engines.items():
                if enabled_engines is not None and engine_name not in enabled_engines:
                    logger.info(f"[{task.id}] Engine '{engine_name}' skipped (strategy)")
                    continue
                logger.info(f"[{task.id}] Starting engine: {engine_name}")
                coro = loop.run_in_executor(
                    self.executor,
                    engine.analyze,
                    clone_dir,
                    diff_files,
                )
                engine_tasks.append((engine_name, coro))

            # Gather results
            for engine_name, coro in engine_tasks:
                try:
                    findings = await coro
                    logger.info(f"[{task.id}] Engine '{engine_name}' found {len(findings)} issues")
                    all_findings.extend(findings)
                except Exception as e:
                    logger.error(f"[{task.id}] Engine '{engine_name}' failed: {e}")

            # AI enrichment (runs after all engines)
            _run_ai = ai_enabled if ai_enabled is not None else (self._ai_engine is not None)
            if _run_ai and self._ai_engine and all_findings:
                logger.info(f"[{task.id}] Running AI enrichment on {len(all_findings)} findings")
                all_findings = self._ai_engine.enrich(all_findings)
                logger.info(f"[{task.id}] AI enrichment complete")

            # Deduplicate findings by (engine, file_path, line, message)
            seen = set()
            deduped = []
            for f in all_findings:
                key = (f.engine, f.file_path, f.line, f.message)
                if key not in seen:
                    seen.add(key)
                    deduped.append(f)
            if len(deduped) < len(all_findings):
                logger.info(f"[{task.id}] Dedup removed {len(all_findings) - len(deduped)} duplicate findings")
            all_findings = deduped

            # Sort by severity
            severity_order = {"blocker": 0, "critical": 1, "major": 2, "minor": 3, "info": 4}
            all_findings.sort(key=lambda f: severity_order.get(f.severity, 5))

            task.findings = all_findings
            task.status = "completed"
            task.completed_at = __import__("datetime").datetime.utcnow()
            logger.info(f"[{task.id}] Scan complete: {len(all_findings)} findings")

        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            logger.error(f"[{task.id}] Scan failed: {e}")
        finally:
            if clone_dir:
                try:
                    self.repo_manager.cleanup(clone_dir)
                except Exception as e:
                    logger.warning(f"[{task.id}] Cleanup warning: {e}")

        return task
