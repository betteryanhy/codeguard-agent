"""Tool for writing knowledge to the knowledge base (SQLite + Chroma)."""

import json
import logging
from datetime import datetime
from typing import Optional

from app.config import settings
from app.tools.base import BaseTool, ToolResult
from app.knowledge.schemas import ProjectBaseline, ModuleRecord, InterfaceRecord, MrRecord

logger = logging.getLogger(__name__)


class KnowledgeWriterTool(BaseTool):
    """Write records to the knowledge base (baseline, MR semantics, code chunks)."""

    @property
    def name(self) -> str:
        return "write_knowledge"

    async def execute(
        self,
        record_type: str = "",
        data: Optional[dict] = None,
        **kwargs,
    ) -> ToolResult:
        """Write a record to the knowledge base.

        Args:
            record_type: One of "mr_record", "code_chunk", "baseline"
            data: Record content as dict

        Returns:
            ToolResult with record ID
        """
        from app.main import knowledge_base
        if not knowledge_base:
            return ToolResult.fail("Knowledge base not initialized")

        data = data or {}

        try:
            if record_type == "mr_record":
                return await self._write_mr_record(knowledge_base, data)
            elif record_type == "code_chunk":
                return await self._write_code_chunk(knowledge_base, data)
            elif record_type == "baseline":
                return await self._write_baseline(knowledge_base, data)
            else:
                return ToolResult.fail(f"Unknown record_type: {record_type}")
        except Exception as e:
            logger.error("Knowledge write failed: %s", e)
            return ToolResult.fail(str(e))

    async def _write_mr_record(self, kb, data: dict) -> ToolResult:
        record = MrRecord(
            repo_url=data.get("repo_url", ""),
            mr_id=data.get("mr_id", 0),
            mr_title=data.get("mr_title", ""),
            mr_description=data.get("mr_description", ""),
            source_branch=data.get("source_branch", ""),
            target_branch=data.get("target_branch", ""),
            author=data.get("author", ""),
            merged_by=data.get("merged_by", ""),
            merged_at=datetime.utcnow(),
            summary=data.get("summary", ""),
            risks=json.dumps(data.get("risks", [])),
            interfaces_changed=json.dumps(data.get("interfaces_changed", [])),
        )
        record_id = kb.save_mr_record(record)

        # Also add semantic to Chroma
        chroma_id = f"mr::{data.get('repo_url', '').split('/')[-1].replace('.git', '')}::{data.get('mr_id', 0)}"
        kb.add_mr_semantic(
            mr_id_str=chroma_id,
            document=data.get("summary", ""),
            metadata={
                "repo_url": data.get("repo_url", ""),
                "mr_id": data.get("mr_id", 0),
                "source_branch": data.get("source_branch", ""),
                "target_branch": data.get("target_branch", ""),
                "author": data.get("author", ""),
            },
        )

        return ToolResult.ok({"record_id": record_id, "chroma_id": chroma_id})

    async def _write_code_chunk(self, kb, data: dict) -> ToolResult:
        chunk_id = data.get("id", "")
        document = data.get("document", "")
        metadata = data.get("metadata", {})
        success = kb.add_code_chunk(chunk_id, document, metadata)
        if success:
            return ToolResult.ok({"chunk_id": chunk_id})
        return ToolResult.fail("Failed to write code chunk")

    async def _write_baseline(self, kb, data: dict) -> ToolResult:
        baseline = ProjectBaseline(
            repo_url=data.get("repo_url", ""),
            default_branch=data.get("default_branch", "master"),
            total_files=data.get("total_files", 0),
            tech_stack=data.get("tech_stack", ""),
            summary=data.get("summary", ""),
        )
        baseline_id = kb.save_baseline(baseline)
        return ToolResult.ok({"baseline_id": baseline_id})
