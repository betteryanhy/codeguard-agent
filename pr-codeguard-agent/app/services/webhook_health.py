"""Webhook health monitoring - check, report, and auto-repair webhook registrations."""

import logging
from datetime import datetime
from typing import Optional

from app.config import settings
from app.services.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


class WebhookHealthEntry:
    """Health snapshot for a single webhook."""

    def __init__(
        self,
        project_id: int,
        project_name: str,
        webhook_id: Optional[int],
        registered: bool,
        healthy: bool = False,
        last_status: str = "unknown",
        recent_failures: int = 0,
        last_delivery_at: Optional[str] = None,
        error_message: str = "",
        auto_fixed: bool = False,
    ):
        self.project_id = project_id
        self.project_name = project_name
        self.webhook_id = webhook_id
        self.registered = registered
        self.healthy = healthy
        self.last_status = last_status
        self.recent_failures = recent_failures
        self.last_delivery_at = last_delivery_at
        self.error_message = error_message
        self.auto_fixed = auto_fixed

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "project_name": self.project_name,
            "webhook_id": self.webhook_id,
            "registered": self.registered,
            "healthy": self.healthy,
            "last_status": self.last_status,
            "recent_failures": self.recent_failures,
            "last_delivery_at": self.last_delivery_at,
            "error_message": self.error_message,
            "auto_fixed": self.auto_fixed,
        }


class WebhookHealthChecker:
    """Periodically check and repair webhook registrations."""

    def __init__(self):
        self._client = GitLabClient()
        self._health_cache: dict[int, WebhookHealthEntry] = {}
        self._last_check: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def check_all(self, projects: list[dict]) -> list[WebhookHealthEntry]:
        """Check webhook health for all discovered projects.

        Args:
            projects: List of project dicts from DiscoveryService.list_discovered().

        Returns:
            List of WebhookHealthEntry with health status.
        """
        results = []
        fixed_count = 0

        for p in projects:
            entry = self._check_single(p)
            if entry.auto_fixed:
                fixed_count += 1
            results.append(entry)
            self._health_cache[p["project_id"]] = entry

        self._last_check = datetime.utcnow()

        healthy = sum(1 for r in results if r.healthy)
        logger.info(
            "Webhook health check: %d/%d healthy, %d auto-fixed",
            healthy, len(results), fixed_count,
        )

        return results

    def _check_single(self, project: dict) -> WebhookHealthEntry:
        """Check and repair a single project's webhook."""
        pid = project["project_id"]
        name = project.get("name_with_namespace", project.get("name", f"project-{pid}"))
        webhook_id = project.get("webhook_id")
        registered = project.get("registered", False)

        if not registered or not webhook_id:
            return WebhookHealthEntry(
                project_id=pid,
                project_name=name,
                webhook_id=webhook_id,
                registered=registered,
                healthy=False,
                last_status="not_registered",
                recent_failures=0,
                error_message="Webhook not registered",
            )

        # Step 1: Get webhook detail (check if it still exists on GitLab)
        try:
            hook = self._client.get_webhook_detail(pid, webhook_id)
            if not hook or hook.get("id") != webhook_id:
                raise ValueError("Webhook not found on GitLab")
        except Exception as e:
            logger.warning("Webhook %d for project %d missing: %s", webhook_id, pid, e)
            return self._try_repair(pid, name, f"Webhook not found: {e}")

        # Step 2: Check recent deliveries
        try:
            deliveries = self._client.list_webhook_deliveries(pid, webhook_id, per_page=5)
        except Exception:
            deliveries = []

        recent_failures = 0
        last_status = "unknown"
        last_delivery_at = None
        error_message = ""

        for d in deliveries:
            status_code = d.get("status", 0)
            created = d.get("created_at", "")
            success = d.get("success", False)
            if created and (last_delivery_at is None or created > last_delivery_at):
                last_delivery_at = created
                last_status = str(status_code)

            if not success:
                recent_failures += 1
                if status_code == 0:
                    error_message = "Delivery failed (no response)"
                else:
                    error_message = f"HTTP {status_code}"

        # Step 3: Auto-repair if too many failures
        if recent_failures >= 3:
            logger.warning(
                "Webhook %d for project %d has %d recent failures, attempting repair",
                webhook_id, pid, recent_failures,
            )
            return self._try_repair(pid, name, f"{recent_failures} consecutive delivery failures")

        # Healthy
        is_healthy = recent_failures == 0
        return WebhookHealthEntry(
            project_id=pid,
            project_name=name,
            webhook_id=webhook_id,
            registered=True,
            healthy=is_healthy,
            last_status=last_status,
            recent_failures=recent_failures,
            last_delivery_at=last_delivery_at,
            error_message=error_message,
        )

    def _try_repair(self, project_id: int, project_name: str, reason: str) -> WebhookHealthEntry:
        """Delete the broken webhook and re-register it."""
        logger.info("Repairing webhook for project %d (%s): %s", project_id, project_name, reason)

        # Delete old webhooks (find them by URL pattern)
        webhook_url = f"http://{settings.host}:{settings.port}/api/v1/webhook/gitlab"
        try:
            hooks = self._client.list_webhooks(project_id)
            for h in hooks:
                if webhook_url in h.get("url", ""):
                    try:
                        self._client.delete_webhook(project_id, h["id"])
                        logger.info("Deleted broken webhook %d for project %d", h["id"], project_id)
                    except Exception as e:
                        logger.warning("Failed to delete webhook %d: %s", h["id"], e)
        except Exception as e:
            logger.warning("Failed to list webhooks for repair: %s", e)

        # Re-register
        try:
            from app.services.discovery_service import DiscoveryService
            ds = DiscoveryService()
            ds.scan_all()
            result = ds.ensure_single_webhook(project_id)
            if result:
                logger.info("Successfully repaired webhook for project %d (%s)", project_id, project_name)
                return WebhookHealthEntry(
                    project_id=project_id,
                    project_name=project_name,
                    webhook_id=None,
                    registered=True,
                    healthy=True,
                    last_status="repaired",
                    recent_failures=0,
                    error_message="",
                    auto_fixed=True,
                )
        except Exception as e:
            logger.warning("Failed to re-register webhook: %s", e)

        return WebhookHealthEntry(
            project_id=project_id,
            project_name=project_name,
            webhook_id=None,
            registered=False,
            healthy=False,
            last_status="repair_failed",
            recent_failures=0,
            error_message=f"Auto-repair failed: {reason}",
        )

    # ------------------------------------------------------------------
    # Status query
    # ------------------------------------------------------------------

    def get_health_summary(self) -> dict:
        """Get summary of current webhook health status."""
        entries = list(self._health_cache.values())
        total = len(entries)
        healthy = sum(1 for e in entries if e.healthy)
        broken = sum(1 for e in entries if not e.healthy)
        auto_fixed = sum(1 for e in entries if e.auto_fixed)

        return {
            "total": total,
            "healthy": healthy,
            "broken": broken,
            "auto_fixed": auto_fixed,
            "health_rate": round(healthy / total * 100, 1) if total > 0 else 0,
            "last_check": self._last_check.isoformat() if self._last_check else None,
        }

    def list_health(self) -> list[dict]:
        """List all webhook health entries."""
        return [e.to_dict() for e in self._health_cache.values()]

    def get_health(self, project_id: int) -> Optional[WebhookHealthEntry]:
        """Get health entry for a single project."""
        return self._health_cache.get(project_id)
