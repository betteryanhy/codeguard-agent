"""Tool to build an initial project baseline understanding.

Traverses the entire repository, uses LLM to understand each file,
identifies modules and interfaces, and stores everything in the knowledge base.
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.tools.base import BaseTool, ToolResult
from app.services.repo_manager import RepoManager
from app.knowledge.schemas import ProjectBaseline, ModuleRecord, InterfaceRecord

logger = logging.getLogger(__name__)

# File extensions to analyze (skip binaries, images, etc.)
ANALYZE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rs", ".rb",
    ".php", ".swift", ".kt", ".scala", ".yaml", ".yml", ".json", ".toml",
    ".ini", ".cfg", ".conf", ".env.example", ".sql", ".graphql", ".proto",
    ".sh", ".bash", ".zsh", ".dockerfile", ".makefile",
}

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".idea", ".vscode", ".trae", "dist", "build", ".tox", ".egg-info",
    "site-packages", ".mypy_cache", ".pytest_cache", ".terraform",
    ".serverless", "aidlc-docs", "data",
}


class BaselineBuilderTool(BaseTool):
    """Build initial project understanding by analyzing all files."""

    @property
    def name(self) -> str:
        return "build_baseline"

    async def execute(
        self,
        repo_url: str = "",
        branch: str = "master",
        local_path: str = "",
        **kwargs,
    ) -> ToolResult:
        """Build a project baseline.

        Args:
            repo_url: Repository URL (used if local_path not provided)
            branch: Branch to clone/clone for analysis
            local_path: Local path to project (skip cloning if provided)

        Returns:
            ToolResult with baseline_id
        """
        clone_dir = None
        try:
            if local_path and os.path.isdir(local_path):
                project_path = local_path
            elif repo_url:
                repo_manager = RepoManager()
                clone_dir = repo_manager.clone_repo(repo_url, branch, 0)
                project_path = clone_dir
            else:
                return ToolResult.fail("Either repo_url or local_path is required")

            from app.main import knowledge_base
            if not knowledge_base:
                return ToolResult.fail("Knowledge base not initialized")

            # 1. Traverse project structure
            files_analyzed = []
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

                rel_root = os.path.relpath(root, project_path)
                if rel_root == ".":
                    rel_root = ""

                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext not in ANALYZE_EXTENSIONS:
                        continue

                    file_path = os.path.join(root, fname)
                    rel_path = os.path.join(rel_root, fname) if rel_root else fname

                    try:
                        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read(4096)  # First 4KB for summary
                        files_analyzed.append({
                            "path": rel_path,
                            "ext": ext,
                            "preview": content[:500],
                        })
                    except Exception as e:
                        logger.debug("Skipping %s: %s", rel_path, e)

            # 2. Use LLM to generate project summary
            summary = self._generate_project_summary(project_path, files_analyzed)

            # 3. Save baseline to SQLite
            baseline = ProjectBaseline(
                repo_url=repo_url or local_path,
                default_branch=branch,
                total_files=len(files_analyzed),
                tech_stack=self._detect_tech_stack(files_analyzed),
                summary=summary,
            )
            baseline_id = knowledge_base.save_baseline(baseline)

            # 4. Add code chunks to Chroma
            chunk_ids = []
            chunk_docs = []
            chunk_metas = []

            for fa in files_analyzed:
                chunk_id = f"file::{fa['path']}::init"
                chunk_ids.append(chunk_id)
                chunk_docs.append(f"File: {fa['path']}\nPreview: {fa['preview']}")
                chunk_metas.append({
                    "file_path": fa["path"],
                    "ext": fa["ext"],
                    "baseline_id": str(baseline_id),
                    "type": "file",
                })

            if chunk_ids:
                knowledge_base.add_code_chunks(chunk_ids, chunk_docs, chunk_metas)

            # 5. Add baseline to Chroma
            knowledge_base.add_mr_semantic(
                mr_id_str=f"baseline::{baseline_id}",
                document=summary,
                metadata={
                    "repo_url": repo_url or local_path,
                    "branch": branch,
                    "baseline_id": baseline_id,
                    "total_files": len(files_analyzed),
                },
            )

            logger.info(
                "Baseline built: %s, %d files, %d chunks",
                repo_url or local_path, len(files_analyzed), len(chunk_ids),
            )

            return ToolResult.ok({
                "baseline_id": baseline_id,
                "total_files": len(files_analyzed),
                "summary": summary[:200] + "..." if len(summary) > 200 else summary,
            })

        except Exception as e:
            logger.error("Baseline build failed: %s", e)
            return ToolResult.fail(str(e))
        finally:
            if clone_dir:
                try:
                    RepoManager().cleanup(clone_dir)
                except Exception:
                    pass

    def _detect_tech_stack(self, files: list[dict]) -> str:
        """Detect technology stack from file extensions."""
        ext_count: dict[str, int] = {}
        for f in files:
            ext = f.get("ext", "")
            if ext:
                ext_count[ext] = ext_count.get(ext, 0) + 1

        # Map extensions to tech names
        tech_map = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".go": "Go", ".java": "Java", ".rs": "Rust",
            ".yaml": "YAML", ".yml": "YAML", ".json": "JSON",
            ".sql": "SQL", ".sh": "Shell",
        }
        detected = set()
        for ext, count in sorted(ext_count.items(), key=lambda x: -x[1]):
            tech = tech_map.get(ext)
            if tech and count >= 2:
                detected.add(tech)

        return ", ".join(sorted(detected)) if detected else "Unknown"

    def _generate_project_summary(self, project_path: str, files: list[dict]) -> str:
        """Generate a project summary. Uses LLM if available, else rule-based."""
        if not settings.ai_enabled or not settings.ai_api_key:
            return self._rule_based_summary(files)

        try:
            import httpx
            file_list = "\n".join(
                f"  {f['path']} ({f['ext']})"
                for f in files[:50]  # Limit to 50 files for prompt size
            )

            prompt = (
                "Analyze this project structure and provide a concise summary:\n"
                f"Total files: {len(files)}\n"
                f"Technology stack: {self._detect_tech_stack(files)}\n\n"
                f"Key files:\n{file_list}\n\n"
                "Provide a brief summary (2-3 sentences) of what this project does."
            )

            resp = httpx.post(
                f"{settings.ai_api_base}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.ai_model,
                    "messages": [
                        {"role": "system", "content": "You are a code analysis expert."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 300,
                },
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()

        except Exception as e:
            logger.warning("LLM summary failed, using rule-based: %s", e)
            return self._rule_based_summary(files)

    def _rule_based_summary(self, files: list[dict]) -> str:
        """Simple rule-based fallback summary."""
        tech = self._detect_tech_stack(files)
        api_files = [f for f in files if any(x in f["path"].lower() for x in ("api", "route", "controller", "view"))]
        model_files = [f for f in files if any(x in f["path"].lower() for x in ("model", "schema", "entity"))]
        config_files = [f for f in files if f["ext"] in (".yaml", ".yml", ".json", ".toml", ".ini", ".cfg")]

        parts = [f"Project with {len(files)} files."]
        if tech:
            parts.append(f"Technologies: {tech}.")
        if api_files:
            parts.append(f"Contains {len(api_files)} API/route definitions.")
        if model_files:
            parts.append(f"Contains {len(model_files)} data models.")
        if config_files:
            parts.append(f"Contains {len(config_files)} configuration files.")

        return " ".join(parts)
