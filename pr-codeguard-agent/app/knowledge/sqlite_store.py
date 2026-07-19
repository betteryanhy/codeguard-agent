"""SQLite storage for structured knowledge data (modules, interfaces, MR records)."""

import json
import sqlite3
import logging
from datetime import datetime
from typing import Optional

from app.knowledge.schemas import (
    ProjectBaseline, ModuleRecord, InterfaceRecord,
    CommitRecord, FileChange, MrRecord,
)

logger = logging.getLogger(__name__)


class SqliteStore:
    """Manages structured data tables for the knowledge base."""

    def __init__(self, db_path: str = "./data/knowledge.db"):
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS project_baseline (
        id INTEGER PRIMARY KEY,
        repo_url TEXT NOT NULL,
        default_branch TEXT,
        total_files INTEGER DEFAULT 0,
        total_modules INTEGER DEFAULT 0,
        tech_stack TEXT,
        summary TEXT,
        created_at TIMESTAMP,
        updated_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS modules (
        id INTEGER PRIMARY KEY,
        baseline_id INTEGER REFERENCES project_baseline(id),
        name TEXT NOT NULL,
        description TEXT,
        relative_path TEXT,
        created_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS interfaces (
        id INTEGER PRIMARY KEY,
        module_id INTEGER REFERENCES modules(id),
        name TEXT NOT NULL,
        type TEXT,
        signature TEXT,
        description TEXT,
        file_path TEXT,
        line_number INTEGER DEFAULT 0,
        created_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS mr_records (
        id INTEGER PRIMARY KEY,
        repo_url TEXT NOT NULL,
        mr_id INTEGER NOT NULL,
        mr_title TEXT,
        mr_description TEXT,
        source_branch TEXT,
        target_branch TEXT,
        author TEXT,
        merged_by TEXT,
        merged_at TIMESTAMP,
        summary TEXT,
        risks TEXT,
        interfaces_changed TEXT,
        chroma_ids TEXT,
        created_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS commit_records (
        id INTEGER PRIMARY KEY,
        mr_id INTEGER NOT NULL,
        repo_url TEXT NOT NULL,
        commit_id TEXT NOT NULL,
        short_id TEXT,
        title TEXT,
        author_name TEXT,
        author_email TEXT,
        committed_date TIMESTAMP,
        additions INTEGER DEFAULT 0,
        deletions INTEGER DEFAULT 0,
        total_changes INTEGER DEFAULT 0,
        files_changed INTEGER DEFAULT 0,
        created_at TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS file_changes (
        id INTEGER PRIMARY KEY,
        mr_id INTEGER NOT NULL,
        repo_url TEXT NOT NULL,
        file_path TEXT NOT NULL,
        old_path TEXT,
        new_file INTEGER DEFAULT 0,
        renamed_file INTEGER DEFAULT 0,
        deleted_file INTEGER DEFAULT 0,
        additions INTEGER DEFAULT 0,
        deletions INTEGER DEFAULT 0,
        diff TEXT,
        created_at TIMESTAMP
    );
    """

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Create tables if they don't exist."""
        conn = self._connect()
        try:
            conn.executescript(self.SCHEMA_SQL)
            conn.commit()
            logger.info("Knowledge SQLite tables initialized")
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # CRUD: Project Baseline
    # ------------------------------------------------------------------

    def save_baseline(self, baseline: ProjectBaseline) -> int:
        conn = self._connect()
        try:
            now = datetime.utcnow()
            baseline.created_at = baseline.created_at or now
            baseline.updated_at = now
            cur = conn.execute(
                """INSERT INTO project_baseline
                   (repo_url, default_branch, total_files, total_modules,
                    tech_stack, summary, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (baseline.repo_url, baseline.default_branch,
                 baseline.total_files, baseline.total_modules,
                 baseline.tech_stack, baseline.summary,
                 baseline.created_at, baseline.updated_at),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_baseline(self, repo_url: str) -> Optional[ProjectBaseline]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM project_baseline WHERE repo_url = ? ORDER BY id DESC LIMIT 1",
                (repo_url,),
            ).fetchone()
            if row:
                return ProjectBaseline(**dict(row))
            return None
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # CRUD: Modules
    # ------------------------------------------------------------------

    def save_module(self, module: ModuleRecord) -> int:
        conn = self._connect()
        try:
            module.created_at = module.created_at or datetime.utcnow()
            cur = conn.execute(
                """INSERT INTO modules (baseline_id, name, description, relative_path, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (module.baseline_id, module.name, module.description,
                 module.relative_path, module.created_at),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_modules(self, baseline_id: int) -> list[ModuleRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM modules WHERE baseline_id = ?", (baseline_id,)
            ).fetchall()
            return [ModuleRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # CRUD: Interfaces
    # ------------------------------------------------------------------

    def save_interface(self, iface: InterfaceRecord) -> int:
        conn = self._connect()
        try:
            iface.created_at = iface.created_at or datetime.utcnow()
            cur = conn.execute(
                """INSERT INTO interfaces
                   (module_id, name, type, signature, description, file_path, line_number, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (iface.module_id, iface.name, iface.type, iface.signature,
                 iface.description, iface.file_path, iface.line_number, iface.created_at),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_interfaces_by_module(self, module_id: int) -> list[InterfaceRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM interfaces WHERE module_id = ?", (module_id,)
            ).fetchall()
            return [InterfaceRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # CRUD: MR Records
    # ------------------------------------------------------------------

    def save_mr_record(self, record: MrRecord) -> int:
        conn = self._connect()
        try:
            record.created_at = record.created_at or datetime.utcnow()
            cur = conn.execute(
                """INSERT INTO mr_records
                   (repo_url, mr_id, mr_title, mr_description, source_branch, target_branch,
                    author, merged_by, merged_at, summary, risks, interfaces_changed, chroma_ids, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.repo_url, record.mr_id, record.mr_title,
                 record.mr_description, record.source_branch, record.target_branch,
                 record.author, record.merged_by, record.merged_at,
                 record.summary, record.risks, record.interfaces_changed,
                 record.chroma_ids, record.created_at),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_mr_records(self, repo_url: str, limit: int = 20) -> list[MrRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM mr_records WHERE repo_url = ? ORDER BY merged_at DESC LIMIT ?",
                (repo_url, limit),
            ).fetchall()
            return [MrRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    def get_mr_record(self, repo_url: str, mr_id: int) -> Optional[MrRecord]:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM mr_records WHERE repo_url = ? AND mr_id = ? ORDER BY id DESC",
                (repo_url, mr_id),
            ).fetchone()
            if row:
                return MrRecord(**dict(row))
            return None
        finally:
            conn.close()

    def update_mr_record(
        self,
        repo_url: str,
        mr_id: int,
        mr_title: str,
        source_branch: str,
        target_branch: str,
        author: str,
        merged_at: Optional[datetime],
        summary: str,
        risks: str,
    ):
        """Update the most recent MR record for a given repo+mr_id."""
        conn = self._connect()
        try:
            # Find the latest record for this MR (by id DESC) and update it
            row = conn.execute(
                "SELECT id FROM mr_records WHERE repo_url = ? AND mr_id = ? ORDER BY id DESC LIMIT 1",
                (repo_url, mr_id),
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE mr_records SET
                       mr_title=?, source_branch=?, target_branch=?,
                       author=?, merged_at=?, summary=?, risks=?, created_at=?
                       WHERE id=?""",
                    (mr_title, source_branch, target_branch,
                     author, merged_at, summary, risks, datetime.utcnow(),
                     row["id"]),
                )
                conn.commit()
                logger.info("Updated MR record !%d for %s", mr_id, repo_url)
        finally:
            conn.close()

    def get_mr_records_by_date(
        self, start_date: datetime, end_date: datetime,
        repo_url: str = "",
    ) -> list[MrRecord]:
        """Get MR records created within a date range (based on created_at).

        Covers both open events and merge events recorded on the same day.
        """
        conn = self._connect()
        try:
            if repo_url:
                rows = conn.execute(
                    """SELECT * FROM mr_records
                       WHERE created_at >= ? AND created_at < ? AND repo_url = ?
                       ORDER BY created_at DESC""",
                    (start_date, end_date, repo_url),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM mr_records
                       WHERE created_at >= ? AND created_at < ?
                       ORDER BY created_at DESC""",
                    (start_date, end_date),
                ).fetchall()
            return [MrRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # CRUD: Commit Records
    # ------------------------------------------------------------------

    def save_commit_record(self, record: CommitRecord) -> int:
        conn = self._connect()
        try:
            record.created_at = record.created_at or datetime.utcnow()
            cur = conn.execute(
                """INSERT INTO commit_records
                   (mr_id, repo_url, commit_id, short_id, title,
                    author_name, author_email, committed_date,
                    additions, deletions, total_changes, files_changed, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record.mr_id, record.repo_url, record.commit_id,
                 record.short_id, record.title,
                 record.author_name, record.author_email, record.committed_date,
                 record.additions, record.deletions,
                 record.total_changes, record.files_changed,
                 record.created_at),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_commits_by_mr(self, repo_url: str, mr_id: int) -> list[CommitRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM commit_records WHERE repo_url = ? AND mr_id = ? ORDER BY committed_date",
                (repo_url, mr_id),
            ).fetchall()
            return [CommitRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    def get_commits_by_date_range(
        self, repo_url: str,
        start_date: datetime, end_date: datetime,
    ) -> list[CommitRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM commit_records
                   WHERE repo_url = ? AND committed_date >= ? AND committed_date <= ?
                   ORDER BY committed_date""",
                (repo_url, start_date, end_date),
            ).fetchall()
            return [CommitRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    def get_all_commits_by_date_range(
        self, start_date: datetime, end_date: datetime,
    ) -> list[CommitRecord]:
        """Get commits from all repos within a date range."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM commit_records
                   WHERE committed_date >= ? AND committed_date <= ?
                   ORDER BY committed_date""",
                (start_date, end_date),
            ).fetchall()
            return [CommitRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    def get_commits_by_author(
        self, repo_url: str, author_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> list[CommitRecord]:
        conn = self._connect()
        try:
            sql = "SELECT * FROM commit_records WHERE repo_url = ? AND author_name = ?"
            params = [repo_url, author_name]
            if start_date:
                sql += " AND committed_date >= ?"
                params.append(start_date)
            if end_date:
                sql += " AND committed_date <= ?"
                params.append(end_date)
            sql += " ORDER BY committed_date"
            rows = conn.execute(sql, params).fetchall()
            return [CommitRecord(**dict(r)) for r in rows]
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # CRUD: File Changes
    # ------------------------------------------------------------------

    def save_file_change(self, fc: FileChange) -> int:
        conn = self._connect()
        try:
            fc.created_at = fc.created_at or datetime.utcnow()
            cur = conn.execute(
                """INSERT INTO file_changes
                   (mr_id, repo_url, file_path, old_path, new_file, renamed_file, deleted_file,
                    additions, deletions, diff, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (fc.mr_id, fc.repo_url, fc.file_path, fc.old_path,
                 int(fc.new_file), int(fc.renamed_file), int(fc.deleted_file),
                 fc.additions, fc.deletions, fc.diff, fc.created_at),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()

    def get_file_changes_by_mr(self, repo_url: str, mr_id: int) -> list[FileChange]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT * FROM file_changes WHERE repo_url = ? AND mr_id = ?",
                (repo_url, mr_id),
            ).fetchall()
            return [FileChange(**dict(r)) for r in rows]
        finally:
            conn.close()
