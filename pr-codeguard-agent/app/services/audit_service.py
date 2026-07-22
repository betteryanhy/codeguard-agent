import uuid
import logging
from datetime import datetime

from app.services.storage import StorageService

logger = logging.getLogger(__name__)
_storage = StorageService()


async def log_action(
    action: str,
    resource_type: str,
    resource_id: str = "",
    user: str = "system",
    details: dict | None = None,
    ip_address: str = "",
):
    """Record an audit event."""
    try:
        entry = {
            "id": uuid.uuid4().hex[:12],
            "action": action,
            "resource_type": resource_type,
            "resource_id": str(resource_id),
            "user": user,
            "details": details or {},
            "ip_address": ip_address,
            "timestamp": datetime.utcnow(),
        }
        await _storage.save_audit_log(entry)
    except Exception as e:
        logger.warning("Failed to record audit log: %s", e)
