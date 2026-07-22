"""Scheduled daily email sender.

Runs a background asyncio task that triggers daily digest generation,
renders the HTML email, and sends it to configured recipients via SMTP.
"""

import asyncio
import logging
import smtplib
import time
from datetime import datetime, timedelta, date

from app.config import settings
from app.services.daily_digest import DailyDigest
from app.services.email_templates import EmailTemplates

logger = logging.getLogger(__name__)

# Retry configuration
MAX_EMAIL_RETRIES = 3
RETRY_BASE_DELAY = 2.0  # seconds


class EmailScheduler:
    """Scheduled daily email sender."""

    def __init__(self):
        self.digest = DailyDigest()
        self.templates = EmailTemplates()
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        """Check if the scheduler task is currently running."""
        return self._task is not None and not self._task.done()

    async def start(self):
        """Start the daily scheduler background task."""
        if self._task and not self._task.done():
            logger.warning("Email scheduler already running")
            return

        self._task = asyncio.create_task(self._run_daily())
        logger.info("Email scheduler started")

    async def stop(self):
        """Cancel the scheduler background task."""
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
            logger.info("Email scheduler stopped")

    async def _run_daily(self):
        """Run daily loop, sending report at configured time."""
        while True:
            now = datetime.utcnow()
            target = now.replace(hour=9, minute=0, second=0, microsecond=0)
            if now >= target:
                target = target + timedelta(days=1)

            sleep_seconds = (target - now).total_seconds()
            logger.info(
                "Next daily email scheduled at %s (in %.0f seconds)",
                target.isoformat(), sleep_seconds,
            )
            await asyncio.sleep(sleep_seconds)

            try:
                await self.send_daily_report()
            except Exception as e:
                logger.error("Daily email sending failed: %s", e)

    async def send_daily_report(self, report_date: date | None = None):
        """Generate and send the daily report email.

        Args:
            report_date: Date for the report (default: yesterday).

        Returns:
            dict with status and recipients info, or None if email is not configured.
        """
        if not self._is_email_configured():
            logger.warning(
                "Email not configured. Set ALERT_SMTP_HOST, ALERT_EMAIL_FROM, "
                "and ALERT_EMAIL_TO in .env"
            )
            return None

        date_str = (report_date or (datetime.utcnow() - timedelta(days=1)).date()).isoformat()

        # Generate digest
        data = await self.digest.generate(report_date)

        # Render email
        html = self.templates.render_daily(data)
        subject = self.templates.render_subject(data)

        # Send
        recipients = settings.alert_email_to or []
        sent_count = 0
        errors = []

        for recipient in recipients:
            try:
                self._send_with_retry(recipient, subject, html)
                sent_count += 1
                logger.info("Daily email sent to %s (date=%s)", recipient, date_str)
            except Exception as e:
                logger.error("Failed to send daily email to %s: %s", recipient, e)
                errors.append({"recipient": recipient, "error": str(e)})

        return {
            "status": "sent" if sent_count > 0 else "failed",
            "date": date_str,
            "sent_count": sent_count,
            "total_recipients": len(recipients),
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_email_configured() -> bool:
        """Check if SMTP email is properly configured."""
        return bool(
            settings.alert_smtp_host
            and settings.alert_email_from
            and settings.alert_email_to
        )

    def _send_with_retry(self, recipient: str, subject: str, html: str):
        """Send email with retry logic for transient failures.

        Retries on temporary SMTP failures (connection refused, timeout, etc.)
        with exponential backoff. Permanent failures (auth error, invalid address)
        are not retried.

        Raises:
            smtplib.SMTPAuthenticationError: On permanent auth failure (no retry).
            smtplib.SMTPRecipientsRefused: On invalid recipient (no retry).
            smtplib.SMTPServerDisconnected: After exhausting retries.
            smtplib.SMTPConnectError: After exhausting retries.
        """
        last_error = None

        for attempt in range(1, MAX_EMAIL_RETRIES + 1):
            try:
                self._send_email(recipient, subject, html)
                return  # Success
            except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused) as e:
                # Permanent failure - do not retry
                logger.error(
                    "Permanent SMTP failure sending to %s (attempt %d/%d): %s",
                    recipient, attempt, MAX_EMAIL_RETRIES, e,
                )
                raise
            except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError,
                    smtplib.SMTPHeloError, smtplib.SMTPDataError,
                    TimeoutError, OSError) as e:
                last_error = e
                if attempt < MAX_EMAIL_RETRIES:
                    delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "SMTP transient failure sending to %s (attempt %d/%d, "
                        "retrying in %.1fs): %s",
                        recipient, attempt, MAX_EMAIL_RETRIES, delay, e,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "SMTP transient failure to %s exhausted after %d attempts: %s",
                        recipient, MAX_EMAIL_RETRIES, e,
                    )

        # All retries exhausted
        raise last_error  # type: ignore[misc]

    @staticmethod
    def _send_email(recipient: str, subject: str, html: str):
        """Send a single email via SMTP.

        Args:
            recipient: Email address of the recipient.
            subject: Email subject line.
            html: HTML content of the email body.
        """
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        msg = MIMEMultipart("alternative")
        msg["From"] = settings.alert_email_from
        msg["To"] = recipient
        msg["Subject"] = subject

        # Plain text fallback
        msg.attach(MIMEText(
            f"PR-CodeGuard Daily Report - {subject}\n\n"
            f"View this email in HTML format for the best experience.",
            "plain", "utf-8",
        ))
        # HTML version
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP(settings.alert_smtp_host, settings.alert_smtp_port) as server:
            if settings.alert_smtp_use_tls:
                server.starttls()
            if settings.alert_smtp_user:
                server.login(settings.alert_smtp_user, settings.alert_smtp_password)
            server.sendmail(settings.alert_email_from, [recipient], msg.as_string())
