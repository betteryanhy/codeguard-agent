"""Data models for project knowledge base."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ------------------------------------------------------------------
# SQLite models (structured data)
# ------------------------------------------------------------------

@dataclass
class ProjectBaseline:
    """Project-level overview, built on first scan."""
    id: Optional[int] = None
    repo_url: str = ""
    default_branch: str = ""
    total_files: int = 0
    total_modules: int = 0
    tech_stack: str = ""
    summary: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ModuleRecord:
    """A business module identified from the codebase."""
    id: Optional[int] = None
    baseline_id: int = 0
    name: str = ""
    description: str = ""
    relative_path: str = ""
    created_at: Optional[datetime] = None


@dataclass
class InterfaceRecord:
    """An API endpoint, function, CLI command, etc."""
    id: Optional[int] = None
    module_id: int = 0
    name: str = ""
    type: str = ""  # api / function / cli / event
    signature: str = ""
    description: str = ""
    file_path: str = ""
    line_number: int = 0
    created_at: Optional[datetime] = None


@dataclass
class CommitRecord:
    """A single commit within an MR."""
    id: Optional[int] = None
    mr_id: int = 0
    repo_url: str = ""
    commit_id: str = ""  # git SHA
    short_id: str = ""
    title: str = ""
    author_name: str = ""
    author_email: str = ""
    committed_date: Optional[datetime] = None
    additions: int = 0
    deletions: int = 0
    total_changes: int = 0
    files_changed: int = 0
    created_at: Optional[datetime] = None


@dataclass
class FileChange:
    """A file-level change record within an MR."""
    id: Optional[int] = None
    mr_id: int = 0
    repo_url: str = ""
    file_path: str = ""
    old_path: str = ""
    new_file: bool = False
    renamed_file: bool = False
    deleted_file: bool = False
    additions: int = 0
    deletions: int = 0
    diff: str = ""
    created_at: Optional[datetime] = None


@dataclass
class MrStats:
    """Aggregated MR statistics."""
    mr_id: int = 0
    repo_url: str = ""
    total_commits: int = 0
    total_additions: int = 0
    total_deletions: int = 0
    total_changes: int = 0
    total_files: int = 0
    author_names: str = ""  # comma-separated


@dataclass
class MrRecord:
    """Semantic record of a merged MR."""
    id: Optional[int] = None
    repo_url: str = ""
    mr_id: int = 0
    mr_title: str = ""
    mr_description: str = ""
    source_branch: str = ""
    target_branch: str = ""
    author: str = ""
    merged_by: str = ""
    merged_at: Optional[datetime] = None
    summary: str = ""  # LLM-generated summary
    risks: str = ""  # JSON list of risk items
    interfaces_changed: str = ""  # JSON list of interface names
    chroma_ids: str = ""  # JSON list of associated Chroma vector IDs
    created_at: Optional[datetime] = None
