"""Alert management API - test alerts, view alert status."""

import logging
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


class TestAlertRequest(BaseModel):
    title: str = "PR-CodeGuard 测试告警"
    message: str = "这是一条来自 PR-CodeGuard Agent 的测试告警消息。\n\n如果收到此消息，说明告警通道配置正确。"


@router.get("/status")
async def alert_status(request: Request):
    """Get alert system status."""
    from app.services.alert_service import AlertService
    alert = AlertService()
    return {
        "configured": alert.is_configured,
        "channel_count": len(alert._channels),
        "severity_threshold": alert._threshold,
        "channels": [
            ch.__class__.__name__.replace("Channel", "").lower()
            for ch in alert._channels
        ],
    }


@router.post("/test")
async def send_test_alert(req: TestAlertRequest):
    """Send a test alert to all configured channels."""
    from app.services.alert_service import AlertService
    alert = AlertService()

    if not alert.is_configured:
        raise HTTPException(status_code=400, detail="No alert channels configured")

    result = alert.notify_text(title=req.title, message=req.message)
    return result


@router.post("/send-report")
async def send_daily_report(
    date_str: str = Query(default="", description="Date in YYYY-MM-DD format, defaults to today"),
):
    """Generate and send a daily report email.

    Creates a full HTML-formatted daily report with MR activity,
    developer contributions, and security findings, then sends it via email.
    """
    from app.services.report_mailer import ReportMailer
    mailer = ReportMailer()
    result = mailer.send_daily_report(date_str if date_str else None)
    return result
