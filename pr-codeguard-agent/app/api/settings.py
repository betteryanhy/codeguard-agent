from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.services.storage import StorageService, UserRecord

router = APIRouter(prefix="/api/v1/system", tags=["system"])
storage = StorageService()


class SettingsUpdate(BaseModel):
    settings: dict


_SENSITIVE_KEYS = {"jwt_secret", "gitlab_api_token", "gitlab_admin_token", "gitlab_bot_token",
                   "webhook_secret", "alert_dingtalk_secret", "alert_slack_webhook",
                   "alert_smtp_password", "ai_api_key"}


def _mask_sensitive(value: str, key: str) -> str:
    """Mask sensitive setting values."""
    if key in _SENSITIVE_KEYS and len(value) > 4:
        return value[:2] + "****" + value[-2:]
    return value


@router.get("/settings")
async def get_settings(current_user: UserRecord = Depends(get_current_user)):
    """Get all settings with sensitive values masked."""
    all_settings = await storage.get_all_settings()
    masked = {k: _mask_sensitive(v, k) for k, v in all_settings.items()}
    return masked


@router.put("/settings")
async def update_settings(
    data: SettingsUpdate,
    current_user: UserRecord = Depends(get_current_user),
):
    """Batch update settings."""
    for key, value in data.settings.items():
        await storage.set_setting(key, str(value))

    from app.services.audit_service import log_action
    await log_action(
        action="settings_updated",
        resource_type="system",
        user=current_user.username,
        details={"keys": list(data.settings.keys())},
    )

    return {"message": "Settings updated successfully", "count": len(data.settings)}


@router.get("/settings/{key}")
async def get_setting(
    key: str,
    current_user: UserRecord = Depends(get_current_user),
):
    """Get a single setting."""
    value = await storage.get_setting(key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    return {"key": key, "value": _mask_sensitive(value, key)}


@router.put("/settings/{key}")
async def update_setting(
    key: str,
    value: str = Body(..., embed=True),
    current_user: UserRecord = Depends(get_current_user),
):
    """Update a single setting."""
    await storage.set_setting(key, value)

    from app.services.audit_service import log_action
    await log_action(
        action="setting_updated",
        resource_type="system",
        resource_id=key,
        user=current_user.username,
    )

    return {"message": f"Setting '{key}' updated successfully"}
