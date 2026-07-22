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
    source_branch: Mapped[str] = mapped_column(String(256), default="")
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


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    username: Mapped[str] = mapped_column(String(128), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32), default="admin")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(128), default="")
    user: Mapped[str] = mapped_column(String(128))
    details_json: Mapped[str] = mapped_column(Text, default="{}")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SettingsRecord(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class StorageService:
    """Async SQLite storage service for tasks and configs."""

    def __init__(self):
        self.engine = create_async_engine(settings.database_url)

    async def init_db(self):
        """Create all tables if they don't exist."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Migrate: add source_branch column if missing
        try:
            async with self.engine.begin() as conn:
                from sqlalchemy import text
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN source_branch VARCHAR(256) DEFAULT ''"))
        except Exception:
            pass  # Column already exists

    # ---- Task operations ----

    async def save_task(self, task: ScanTask):
        """Save or update a scan task."""
        record = TaskRecord(
            id=task.id,
            repo_url=task.repo_url,
            mr_id=task.mr_id,
            mr_title=task.mr_title,
            source_branch=task.source_branch,
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
                source_branch=record.source_branch or "",
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
                    source_branch=record.source_branch or "",
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

    # ---- User operations ----

    async def save_user(self, user: UserRecord):
        """Save a user record."""
        async with AsyncSession(self.engine) as session:
            await session.merge(user)
            await session.commit()

    async def get_user(self, user_id: str) -> UserRecord | None:
        """Get a user by ID."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(UserRecord).where(UserRecord.id == user_id)
            )
            return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> UserRecord | None:
        """Get a user by username."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(UserRecord).where(UserRecord.username == username)
            )
            return result.scalar_one_or_none()

    # ---- Audit log operations ----

    async def save_audit_log(self, entry: dict):
        """Save an audit log entry."""
        record = AuditLogRecord(
            id=entry["id"],
            action=entry["action"],
            resource_type=entry["resource_type"],
            resource_id=entry.get("resource_id", ""),
            user=entry["user"],
            details_json=json.dumps(entry.get("details", {}), default=str),
            ip_address=entry.get("ip_address", ""),
            timestamp=entry.get("timestamp", datetime.utcnow()),
        )
        async with AsyncSession(self.engine) as session:
            session.add(record)
            await session.commit()

    async def list_audit_logs(
        self, limit: int = 50, offset: int = 0,
        action: str = "", resource_type: str = "",
    ) -> tuple[list[dict], int]:
        """List audit logs with optional filters. Returns (items, total)."""
        async with AsyncSession(self.engine) as session:
            query = select(AuditLogRecord)
            count_query = select(AuditLogRecord)

            if action:
                query = query.where(AuditLogRecord.action == action)
                count_query = count_query.where(AuditLogRecord.action == action)
            if resource_type:
                query = query.where(AuditLogRecord.resource_type == resource_type)
                count_query = count_query.where(AuditLogRecord.resource_type == resource_type)

            # Get total count
            count_result = await session.execute(count_query)
            total = len(count_result.scalars().all())

            # Get paginated results
            result = await session.execute(
                query.order_by(AuditLogRecord.timestamp.desc())
                .offset(offset)
                .limit(limit)
            )
            records = result.scalars().all()

            items = []
            for r in records:
                items.append({
                    "id": r.id,
                    "action": r.action,
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "user": r.user,
                    "details": json.loads(r.details_json) if r.details_json else {},
                    "ip_address": r.ip_address,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                })
            return items, total

    # ---- Settings operations ----

    async def get_setting(self, key: str) -> str | None:
        """Get a system setting value by key."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(
                select(SettingsRecord).where(SettingsRecord.key == key)
            )
            record = result.scalar_one_or_none()
            return record.value if record else None

    async def set_setting(self, key: str, value: str):
        """Set a system setting value."""
        record = SettingsRecord(
            key=key,
            value=value,
            updated_at=datetime.utcnow(),
        )
        async with AsyncSession(self.engine) as session:
            await session.merge(record)
            await session.commit()

    async def get_all_settings(self) -> dict:
        """Get all system settings as a dict."""
        async with AsyncSession(self.engine) as session:
            result = await session.execute(select(SettingsRecord))
            records = result.scalars().all()
            return {r.key: r.value for r in records}
