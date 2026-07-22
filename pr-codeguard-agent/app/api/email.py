"""Email API - trigger daily report emails on demand."""
import logging
from datetime import datetime, date
from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/email", tags=["email"])


@router.post("/send")
async def send_email_report():
    """Send a daily report email immediately (for testing/demo)."""
    from app.services.email_scheduler import EmailScheduler
    scheduler = EmailScheduler()
    result = await scheduler.send_daily_report(report_date=datetime.utcnow().date())
    if result is None:
        return {"status": "not_configured", "message": "Email not configured"}
    return result
