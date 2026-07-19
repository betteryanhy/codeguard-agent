import pytest
from app.models.task import ScanTask
from app.utils.helpers import generate_task_id


class TestOrchestrator:
    def test_orchestrator_init(self):
        from app.services.orchestrator import Orchestrator
        orch = Orchestrator()
        assert len(orch.enabled_engines) > 0

    def test_orchestrator_engines_loaded(self):
        from app.services.orchestrator import Orchestrator
        orch = Orchestrator()
        for engine_name in ["secrets", "sast", "iac", "best_practice"]:
            assert engine_name in orch.enabled_engines

    @pytest.mark.asyncio
    async def test_orchestrator_scan_nonexistent_repo(self):
        from app.services.orchestrator import Orchestrator
        orch = Orchestrator()
        task = ScanTask(
            id=generate_task_id(),
            repo_url="http://gitlab/nonexistent/repo.git",
            mr_id=1,
        )
        result = await orch.run_scan(task, "main", "main")
        assert result.status == "failed"
        assert result.findings == []
