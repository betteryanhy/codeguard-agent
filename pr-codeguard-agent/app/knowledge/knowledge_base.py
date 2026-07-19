"""Unified entry point for the knowledge base (SQLite + Chroma)."""

import logging
from datetime import datetime
from typing import Optional

from app.knowledge.sqlite_store import SqliteStore
from app.knowledge.chroma_store import ChromaStore
from app.knowledge.schemas import (
    ProjectBaseline, ModuleRecord, InterfaceRecord, MrRecord,
    CommitRecord, FileChange,
)

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Combines structured (SQLite) and semantic (Chroma) storage."""

    def __init__(self, db_path: str = "./data/knowledge.db", chroma_dir: str = "./data/chroma"):
        self.sqlite = SqliteStore(db_path)
        self.chroma = ChromaStore(chroma_dir)

    def init(self):
        """Initialize both stores."""
        self.sqlite.init_db()
        self.chroma.init_store()
        logger.info("KnowledgeBase initialized")

    # ------------------------------------------------------------------
    # Baseline
    # ------------------------------------------------------------------

    def save_baseline(self, baseline: ProjectBaseline) -> int:
        return self.sqlite.save_baseline(baseline)

    def get_baseline(self, repo_url: str) -> Optional[ProjectBaseline]:
        return self.sqlite.get_baseline(repo_url)

    # ------------------------------------------------------------------
    # Modules
    # ------------------------------------------------------------------

    def save_module(self, module: ModuleRecord) -> int:
        return self.sqlite.save_module(module)

    def get_modules(self, baseline_id: int) -> list[ModuleRecord]:
        return self.sqlite.get_modules(baseline_id)

    # ------------------------------------------------------------------
    # Interfaces
    # ------------------------------------------------------------------

    def save_interface(self, iface: InterfaceRecord) -> int:
        return self.sqlite.save_interface(iface)

    def get_interfaces_by_module(self, module_id: int) -> list[InterfaceRecord]:
        return self.sqlite.get_interfaces_by_module(module_id)

    # ------------------------------------------------------------------
    # MR Records
    # ------------------------------------------------------------------

    def save_mr_record(self, record: MrRecord) -> int:
        return self.sqlite.save_mr_record(record)

    def get_mr_records(self, repo_url: str, limit: int = 20) -> list[MrRecord]:
        return self.sqlite.get_mr_records(repo_url, limit)

    def get_mr_record(self, repo_url: str, mr_id: int) -> Optional[MrRecord]:
        return self.sqlite.get_mr_record(repo_url, mr_id)

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
        return self.sqlite.update_mr_record(
            repo_url, mr_id, mr_title, source_branch, target_branch,
            author, merged_at, summary, risks,
        )

    def get_mr_records_by_date(
        self, start_date, end_date, repo_url: str = "",
    ) -> list[MrRecord]:
        return self.sqlite.get_mr_records_by_date(start_date, end_date, repo_url)

    # ------------------------------------------------------------------
    # Commit Records
    # ------------------------------------------------------------------

    def save_commit_record(self, record: CommitRecord) -> int:
        return self.sqlite.save_commit_record(record)

    def get_commits_by_mr(self, repo_url: str, mr_id: int) -> list[CommitRecord]:
        return self.sqlite.get_commits_by_mr(repo_url, mr_id)

    def get_commits_by_author(
        self, repo_url: str, author_name: str,
        start_date=None, end_date=None,
    ) -> list[CommitRecord]:
        return self.sqlite.get_commits_by_author(repo_url, author_name, start_date, end_date)

    def get_commits_by_date_range(
        self, repo_url: str,
        start_date=None, end_date=None,
    ) -> list[CommitRecord]:
        return self.sqlite.get_commits_by_date_range(repo_url, start_date, end_date)

    def get_all_commits_by_date_range(
        self, start_date=None, end_date=None,
    ) -> list[CommitRecord]:
        return self.sqlite.get_all_commits_by_date_range(start_date, end_date)

    # ------------------------------------------------------------------
    # File Changes
    # ------------------------------------------------------------------

    def save_file_change(self, fc: FileChange) -> int:
        return self.sqlite.save_file_change(fc)

    def get_file_changes_by_mr(self, repo_url: str, mr_id: int) -> list[FileChange]:
        return self.sqlite.get_file_changes_by_mr(repo_url, mr_id)

    # ------------------------------------------------------------------
    # Chroma (semantic search)
    # ------------------------------------------------------------------

    def add_code_chunk(self, chunk_id: str, document: str, metadata: dict) -> bool:
        return self.chroma.add_code_chunk(chunk_id, document, metadata)

    def add_code_chunks(self, ids: list[str], documents: list[str], metadatas: list[dict]) -> bool:
        return self.chroma.add_code_chunks(ids, documents, metadatas)

    def add_mr_semantic(self, mr_id_str: str, document: str, metadata: dict) -> bool:
        return self.chroma.add_mr_semantic(mr_id_str, document, metadata)

    def search_code(self, query: str, n_results: int = 5, filter: Optional[dict] = None) -> list[dict]:
        return self.chroma.search_code(query, n_results, filter)

    def search_mr(self, query: str, n_results: int = 5, filter: Optional[dict] = None) -> list[dict]:
        return self.chroma.search_mr(query, n_results, filter)
