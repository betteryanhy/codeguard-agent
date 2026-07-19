import json
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select, String, Text, Integer, DateTime, Boolean
from app.config import settings
from app.models.task import ScanTask
from app.models.finding import Finding
from app.models.repository import RepoConfig


class Base(DeclarativeBase):
    pass


class TaskRecord(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    repo_url: Mapped[str] = mapped_column(String(512))
    mr_id: Mapped[int] = mapped_column(Integer)
    mr_title: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str] = mapped_column(Text, default="")
    findings_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RepoConfigRecord(Base):
    __tablename__ = "repo_configs"

    repo_url: Mapped[str] = mapped_column(String(512), primary_key=True)
    enabled_engines_json: Mapped[str] = mapped_column(Text, default='["secrets", "sast", "iac", "best_practice"]')
    webhook_secret: Mapped[str] = mapped_column(String(128), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class StorageService:
    """Async SQLite storage service for tasks and configs."""

    def __init__(self):
        self.engine = create_async_engine(settings.database_url)

    async def init_db(self):
        """Create all tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    # ---- Task operations ----

    async def save_task(self, task: ScanTask):
        """Save or update a scan task."""
        record = TaskRecord(
            id=task.id,
            repo_url=task.repo_url,
            mr_id=task.mr_id,
            mr_title=task.mr_title,
            status=task.status,
            error_message=task.error_message,
            findings_json=json.dumps([f.model_dump() for f in task.findings], default=str),
            created_at=task.created_at,
            completed_at=task.completed_at,
        )
        async with AsyncSession(self.engine) as session:
            await session.merge(record)
            await session.commit()

    async def get_task(self, task_id: str) -> ScanTask | None:
        """Get a task by ID."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(TaskRecord).where(TaskRecord.id == task_id)
            )
            record = result.scalar_one_or_none()
            if not record:
                return None

            findings_data = json.loads(record.findings_json) if record.findings_json else []
            findings = [Finding(**f) for f in findings_data]

            return ScanTask(
                id=record.id,
                repo_url=record.repo_url,
                mr_id=record.mr_id,
                mr_title=record.mr_title,
                status=record.status,
                error_message=record.error_message,
                findings=findings,
                created_at=record.created_at,
                completed_at=record.completed_at,
            )

    async def list_tasks(self, limit: int = 50, offset: int = 0) -> list[ScanTask]:
        """List recent tasks."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(TaskRecord)
                .order_by(TaskRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            records = result.scalars().all()
            tasks = []
            for record in records:
                findings_data = json.loads(record.findings_json) if record.findings_json else []
                findings = [Finding(**f) for f in findings_data]
                tasks.append(ScanTask(
                    id=record.id,
                    repo_url=record.repo_url,
                    mr_id=record.mr_id,
                    mr_title=record.mr_title,
                    status=record.status,
                    error_message=record.error_message,
                    findings=findings,
                    created_at=record.created_at,
                    completed_at=record.completed_at,
                ))
            return tasks

    # ---- Config operations ----

    async def save_config(self, config: RepoConfig):
        """Save or update a repository config."""
        record = RepoConfigRecord(
            repo_url=config.repo_url,
            enabled_engines_json=json.dumps(config.enabled_engines),
            webhook_secret=config.webhook_secret,
            active=config.active,
        )
        async with AsyncSession(self.engine) as session:
            await session.merge(record)
            await session.commit()

    async def get_config(self, repo_url: str) -> RepoConfig | None:
        """Get a repository config by URL."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(RepoConfigRecord).where(RepoConfigRecord.repo_url == repo_url)
            )
            record = result.scalar_one_or_none()
            if not record:
                return None
            return RepoConfig(
                repo_url=record.repo_url,
                enabled_engines=json.loads(record.enabled_engines_json),
                webhook_secret=record.webhook_secret,
                active=record.active,
            )

    async def list_configs(self) -> list[RepoConfig]:
        """List all repository configs."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(select(RepoConfigRecord))
            records = result.scalars().all()
            return [
                RepoConfig(
                    repo_url=r.repo_url,
                    enabled_engines=json.loads(r.enabled_engines_json),
                    webhook_secret=r.webhook_secret,
                    active=r.active,
                )
                for r in records
            ]
