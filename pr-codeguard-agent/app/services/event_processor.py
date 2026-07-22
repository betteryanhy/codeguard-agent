"""Process GitLab push/MR/branch events and store in knowledge base.

Handles webhook payloads from GitLab's Push Events, Merge Request Events,
and Branch-related system hooks. Stores structured records (commits, MRs,
file changes, branch operations) into the KnowledgeBase for later querying.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from app.knowledge.knowledge_base import KnowledgeBase
from app.knowledge.schemas import CommitRecord, MrRecord, FileChange

logger = logging.getLogger(__name__)


class BranchEvent:
    """Simple record of a branch create/delete event (in-memory store)."""
    def __init__(
        self,
        project_path: str,
        branch: str,
        action: str,  # "create" or "delete"
        actor: str,
        timestamp: Optional[datetime] = None,
    ):
        self.project_path = project_path
        self.branch = branch
        self.action = action
        self.actor = actor
        self.timestamp = timestamp or datetime.utcnow()


class EventProcessor:
    """Process GitLab system events and store in knowledge base."""

    def __init__(self):
        self.kb = KnowledgeBase()
        self._branch_events: list[BranchEvent] = []

    async def process(self, event_type: str, payload: dict) -> None:
        """Route an event to its handler based on event type.

        Args:
            event_type: Event type string (push, tag_push, merge_request, etc.)
            payload: Full event payload from GitLab webhook.
        """
        handler_map = {
            "push": self._handle_push,
            "tag_push": self._handle_tag_push,
            "merge_request": self._handle_merge_request,
            "repository_update": self._handle_repo_update,
            "branch_create": self._handle_branch_create,
            "branch_delete": self._handle_branch_delete,
        }
        handler = handler_map.get(event_type)
        if handler:
            await handler(payload)
            logger.debug("Processed event: %s", event_type)
        else:
            logger.debug("No handler for event type: %s", event_type)

    # ------------------------------------------------------------------
    # Push event
    # ------------------------------------------------------------------

    async def _handle_push(self, payload: dict) -> None:
        """Store push event commits into knowledge base.

        GitLab Push Event payload structure:
          - ref: "refs/heads/main"
          - user_name / user_email
          - project: { path_with_namespace, http_url }
          - commits: [{ id, message, added, modified, removed }]
        """
        project_path = payload.get("project", {}).get("path_with_namespace", "")
        repo_url = payload.get("project", {}).get("http_url", "")
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else ""
        user = payload.get("user_name", "")
        user_email = payload.get("user_email", "")
        commits = payload.get("commits", [])

        if not commits:
            logger.debug("Push event with no commits, skipping")
            return

        for commit in commits:
            commit_id = commit.get("id", "")
            short_id = commit_id[:12] if commit_id else ""
            message = commit.get("message", "").split("\n")[0]
            added = commit.get("added", [])
            modified = commit.get("modified", [])
            removed = commit.get("removed", [])
            all_files = list(set(added + modified + removed))
            timestamp_str = commit.get("timestamp", "")
            committed_date = None
            if timestamp_str:
                try:
                    committed_date = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError):
                    committed_date = datetime.utcnow()

            record = CommitRecord(
                repo_url=repo_url,
                commit_id=commit_id,
                short_id=short_id,
                title=message,
                author_name=user,
                author_email=user_email,
                committed_date=committed_date,
                additions=len(added),
                deletions=len(removed),
                total_changes=len(all_files),
                files_changed=len(all_files),
            )
            self.kb.save_commit_record(record)

        logger.info(
            "Stored %d commit(s) from push to %s (%s)",
            len(commits), project_path, branch,
        )

    async def _handle_tag_push(self, payload: dict) -> None:
        """Handle tag push events (store as commit records)."""
        ref = payload.get("ref", "")
        tag = ref.replace("refs/tags/", "") if ref else ""
        project_path = payload.get("project", {}).get("path_with_namespace", "")
        user = payload.get("user_name", "")
        logger.info("Tag push: %s on %s by %s", tag, project_path, user)

    # ------------------------------------------------------------------
    # Merge Request event
    # ------------------------------------------------------------------

    async def _handle_merge_request(self, payload: dict) -> None:
        """Store MR event into knowledge base.

        GitLab MR Event payload structure:
          - object_attributes: { id, iid, title, description, source_branch,
                                 target_branch, state, action, merged_by, ... }
          - project: { path_with_namespace, http_url }
          - user: { name }
        """
        obj = payload.get("object_attributes", {})
        project = payload.get("project", {})
        repo_url = project.get("http_url", "")
        project_path = project.get("path_with_namespace", "")

        mr_id = obj.get("iid", 0)
        mr_title = obj.get("title", "")
        mr_description = obj.get("description", "") or ""
        source_branch = obj.get("source_branch", "")
        target_branch = obj.get("target_branch", "")
        author = obj.get("author", {}).get("name", "") or payload.get("user", {}).get("name", "")
        state = obj.get("state", "")
        action = obj.get("action", "")
        merged_by = obj.get("merged_by", {}).get("name", "") if isinstance(obj.get("merged_by"), dict) else ""

        # Determine if merged and when
        merged_at = None
        if state == "merged":
            updated_at_str = obj.get("updated_at", "")
            if updated_at_str:
                try:
                    merged_at = datetime.fromisoformat(
                        updated_at_str.replace("Z", "+00:00")
                    ) if isinstance(updated_at_str, str) else None
                except (ValueError, TypeError):
                    pass

        # Build summary from action and state
        summary_parts = [f"MR !{mr_id}"]
        if action:
            summary_parts.append(action)
        if state:
            summary_parts.append(f"({state})")
        summary_parts.append(mr_title)
        summary = " - ".join(summary_parts)

        record = MrRecord(
            repo_url=repo_url,
            mr_id=mr_id,
            mr_title=mr_title,
            mr_description=mr_description,
            source_branch=source_branch,
            target_branch=target_branch,
            author=author,
            merged_by=merged_by,
            merged_at=merged_at,
            summary=summary,
            risks="",
            interfaces_changed="",
            chroma_ids="",
        )
        self.kb.save_mr_record(record)

        # Store MR description in Chroma for semantic search
        if mr_description:
            doc_text = f"MR !{mr_id}: {mr_title}\n{mr_description}"
            self.kb.add_mr_semantic(
                f"mr_{project_path}_{mr_id}",
                doc_text,
                {
                    "repo_url": repo_url,
                    "project_path": project_path,
                    "mr_id": mr_id,
                    "author": author,
                    "type": "merge_request",
                },
            )

        logger.info(
            "Stored MR event: !%d %s (%s/%s) by %s",
            mr_id, mr_title, project_path, action, author,
        )

    async def _handle_repo_update(self, payload: dict) -> None:
        """Handle repository update events."""
        project_path = payload.get("project", {}).get("path_with_namespace", "")
        logger.info("Repository updated: %s", project_path)

    # ------------------------------------------------------------------
    # Branch events
    # ------------------------------------------------------------------

    async def _handle_branch_create(self, payload: dict) -> None:
        """Handle branch create events."""
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else ""
        project_path = payload.get("project", {}).get("path_with_namespace", "")
        user = payload.get("user_name", "") or payload.get("user", {}).get("name", "")

        event = BranchEvent(
            project_path=project_path,
            branch=branch,
            action="create",
            actor=user,
        )
        self._branch_events.append(event)
        logger.info("Branch created: %s/%s by %s", project_path, branch, user)

    async def _handle_branch_delete(self, payload: dict) -> None:
        """Handle branch delete events."""
        ref = payload.get("ref", "")
        branch = ref.replace("refs/heads/", "") if ref else ""
        project_path = payload.get("project", {}).get("path_with_namespace", "")
        user = payload.get("user_name", "") or payload.get("user", {}).get("name", "")

        event = BranchEvent(
            project_path=project_path,
            branch=branch,
            action="delete",
            actor=user,
        )
        self._branch_events.append(event)
        logger.info("Branch deleted: %s/%s by %s", project_path, branch, user)

    # ------------------------------------------------------------------
    # Query helpers for branch events
    # ------------------------------------------------------------------

    def get_branch_events(
        self,
        project_path: str = "",
        branch: str = "",
        limit: int = 20,
    ) -> list[BranchEvent]:
        """Get branch create/delete events, optionally filtered."""
        results = list(self._branch_events)
        if project_path:
            results = [e for e in results if e.project_path == project_path]
        if branch:
            results = [e for e in results if e.branch == branch]
        results.sort(key=lambda e: e.timestamp, reverse=True)
        return results[:limit]

    def get_all_branch_events(self, limit: int = 50) -> list[BranchEvent]:
        """Get all branch events."""
        return sorted(
            self._branch_events,
            key=lambda e: e.timestamp,
            reverse=True,
        )[:limit]
