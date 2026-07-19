import pytest
from app.models.task import ScanTask
from app.models.finding import Finding
from app.models.repository import RepoConfig
from app.utils.helpers import generate_task_id


@pytest.mark.asyncio
async def test_storage_init():
    from app.services.storage import StorageService
    storage = StorageService()
    await storage.init_db()
    # Should not raise


@pytest.mark.asyncio
async def test_save_and_get_task():
    from app.services.storage import StorageService
    storage = StorageService()
    await storage.init_db()

    task = ScanTask(
        id=generate_task_id(),
        repo_url="http://gitlab/test/repo.git",
        mr_id=1,
        mr_title="Test MR",
        status="pending",
    )
    await storage.save_task(task)

    retrieved = await storage.get_task(task.id)
    assert retrieved is not None
    assert retrieved.id == task.id
    assert retrieved.repo_url == task.repo_url
    assert retrieved.mr_id == task.mr_id


@pytest.mark.asyncio
async def test_save_task_with_findings():
    from app.services.storage import StorageService
    storage = StorageService()
    await storage.init_db()

    task = ScanTask(
        id=generate_task_id(),
        repo_url="http://gitlab/test/repo.git",
        mr_id=2,
        status="completed",
        findings=[
            Finding(
                engine="secrets",
                severity="critical",
                file_path="src/config.py",
                line=10,
                message="Hardcoded secret",
            )
        ],
    )
    await storage.save_task(task)

    retrieved = await storage.get_task(task.id)
    assert retrieved is not None
    assert len(retrieved.findings) == 1
    assert retrieved.findings[0].engine == "secrets"


@pytest.mark.asyncio
async def test_list_tasks():
    from app.services.storage import StorageService
    storage = StorageService()
    await storage.init_db()

    await storage.save_task(ScanTask(id=generate_task_id(), repo_url="http://gitlab/a.git", mr_id=1))
    await storage.save_task(ScanTask(id=generate_task_id(), repo_url="http://gitlab/b.git", mr_id=2))

    tasks = await storage.list_tasks()
    assert len(tasks) >= 2


@pytest.mark.asyncio
async def test_save_and_get_config():
    from app.services.storage import StorageService
    storage = StorageService()
    await storage.init_db()

    config = RepoConfig(
        repo_url="http://gitlab/test/repo.git",
        enabled_engines=["secrets", "sast"],
        active=True,
    )
    await storage.save_config(config)

    retrieved = await storage.get_config(config.repo_url)
    assert retrieved is not None
    assert retrieved.repo_url == config.repo_url
    assert retrieved.enabled_engines == ["secrets", "sast"]
    assert retrieved.active is True
