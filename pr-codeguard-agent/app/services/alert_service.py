"""Alert service - sends notifications to DingTalk, Slack, and Email.

Usage:
    alert = AlertService()
    alert.notify(findings, repo_url="...", mr_id=123, mr_title="...")
"""

import json
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import httpx

from app.config import settings
from app.models.finding import Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Severity hierarchy (higher index = more severe)
# ---------------------------------------------------------------------------
SEVERITY_ORDER = ["info", "minor", "major", "critical", "blocker"]


def _severity_index(severity: str) -> int:
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return -1


def _findings_summary(findings: list[Finding]) -> str:
    """Build a short summary string from findings."""
    counts = {}
    for f in findings:
        sev = f.severity.lower()
        counts[sev] = counts.get(sev, 0) + 1
    parts = [f"{k}={v}" for k, v in sorted(counts.items())]
    return ", ".join(parts) if parts else "0 issues"


# ---------------------------------------------------------------------------
# Base / Channel classes
# ---------------------------------------------------------------------------


class AlertChannel:
    """Base class for alert channels."""

    def send(self, title: str, message: str) -> bool:
        raise NotImplementedError


class DingTalkChannel(AlertChannel):
    """Send alerts via DingTalk robot webhook."""

    def __init__(self, webhook_url: str, secret: str = ""):
        self._webhook_url = webhook_url
        self._secret = secret

    def send(self, title: str, message: str) -> bool:
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": title[:64],
                "text": message,
            },
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(self._webhook_url, json=payload)
                resp.raise_for_status()
                result = resp.json()
                if result.get("errcode") != 0:
                    logger.warning("DingTalk alert failed: %s", result.get("errmsg", ""))
                    return False
                logger.info("DingTalk alert sent: %s", title[:60])
                return True
        except Exception as e:
            logger.warning("DingTalk alert error: %s", e)
            return False


class SlackChannel(AlertChannel):
    """Send alerts via Slack Incoming Webhook."""

    def __init__(self, webhook_url: str):
        self._webhook_url = webhook_url

    def send(self, title: str, message: str) -> bool:
        payload = {
            "text": f"*{title}*\n{message}",
            "mrkdwn": True,
        }
        try:
            with httpx.Client(timeout=15) as client:
                resp = client.post(self._webhook_url, json=payload)
                resp.raise_for_status()
                logger.info("Slack alert sent: %s", title[:60])
                return True
        except Exception as e:
            logger.warning("Slack alert error: %s", e)
            return False


class EmailChannel(AlertChannel):
    """Send alerts via SMTP email."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_addr: str,
        to_addrs: list[str],
        use_tls: bool = True,
    ):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_addr = from_addr
        self._to_addrs = to_addrs
        self._use_tls = use_tls

    def send(self, title: str, message: str) -> bool:
        try:
            msg = MIMEMultipart()
            msg["From"] = self._from_addr
            msg["To"] = ", ".join(self._to_addrs)
            msg["Subject"] = title
            msg.attach(MIMEText(message, "plain", "utf-8"))

            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30) as server:
                if self._use_tls:
                    server.starttls()
                if self._smtp_user:
                    server.login(self._smtp_user, self._smtp_password)
                server.sendmail(self._from_addr, self._to_addrs, msg.as_string())

            logger.info("Email alert sent: %s", title[:60])
            return True
        except Exception as e:
            logger.warning("Email alert error: %s", e)
            return False


# ---------------------------------------------------------------------------
# AlertService
# ---------------------------------------------------------------------------

SEVERITY_ORDER_ALERT = ["info", "minor", "major", "critical", "blocker"]


class AlertService:
    """Aggregates findings and dispatches alerts through configured channels.

    Reads channel configuration from Settings automatically.
    Only fires for findings at or above the configured severity threshold.
    """

    def __init__(self):
        self._channels: list[AlertChannel] = []
        self._threshold = settings.alert_severity_threshold
        self._init_channels()

    def _init_channels(self):
        """Initialize channels based on settings."""
        # DingTalk
        if settings.alert_dingtalk_webhook:
            self._channels.append(
                DingTalkChannel(
                    settings.alert_dingtalk_webhook,
                    settings.alert_dingtalk_secret,
                ),
            )
            logger.info("Alert channel: DingTalk enabled")

        # Slack
        if settings.alert_slack_webhook:
            self._channels.append(
                SlackChannel(settings.alert_slack_webhook),
            )
            logger.info("Alert channel: Slack enabled")

        # Email
        if settings.alert_smtp_host and settings.alert_email_to:
            self._channels.append(
                EmailChannel(
                    smtp_host=settings.alert_smtp_host,
                    smtp_port=settings.alert_smtp_port,
                    smtp_user=settings.alert_smtp_user,
                    smtp_password=settings.alert_smtp_password,
                    from_addr=settings.alert_email_from,
                    to_addrs=settings.alert_email_to,
                    use_tls=settings.alert_smtp_use_tls,
                ),
            )
            logger.info("Alert channel: Email enabled")

        if not self._channels:
            logger.info("No alert channels configured (set ALERT_DINGTALK_WEBHOOK, ALERT_SLACK_WEBHOOK, or ALERT_SMTP_HOST)")

    @property
    def is_configured(self) -> bool:
        """Whether at least one alert channel is configured."""
        return len(self._channels) > 0

    def has_severity_threshold_met(self, findings: list[Finding]) -> bool:
        """Check if any finding meets or exceeds the severity threshold."""
        threshold_idx = _severity_index(self._threshold)
        if threshold_idx < 0:
            threshold_idx = 3  # default: critical
        for f in findings:
            if _severity_index(f.severity.lower()) >= threshold_idx:
                return True
        return False

    # ------------------------------------------------------------------
    # Public send methods
    # ------------------------------------------------------------------

    def notify(
        self,
        findings: list[Finding],
        repo_url: str = "",
        mr_id: Optional[int] = None,
        mr_title: str = "",
        source_branch: str = "",
        target_branch: str = "",
        author: str = "",
    ) -> dict:
        """Send alert if findings meet the severity threshold.

        Args:
            findings: List of scan findings.
            repo_url: Git repository URL.
            mr_id: Merge Request IID.
            mr_title: MR title.
            source_branch: Source branch name.
            target_branch: Target branch name.
            author: MR author name.

        Returns:
            Dict with summary of alert actions taken.
        """
        if not self.is_configured:
            return {"status": "skipped", "reason": "no channels configured"}

        if not self.has_severity_threshold_met(findings):
            return {"status": "skipped", "reason": f"no findings >= {self._threshold}"}

        # Build alert content
        title = self._build_title(repo_url, mr_id, mr_title)
        message = self._build_message(
            findings, repo_url, mr_id, mr_title,
            source_branch, target_branch, author,
        )

        # Dispatch to all channels
        results = {}
        all_ok = True
        for ch in self._channels:
            channel_name = ch.__class__.__name__.replace("Channel", "").lower()
            ok = ch.send(title, message)
            results[channel_name] = "ok" if ok else "failed"
            if not ok:
                all_ok = False

        logger.info(
            "Alert dispatched: %s | findings=%d channels=%s",
            title[:60], len(findings), results,
        )
        return {"status": "sent" if all_ok else "partial", "channels": results}

    def notify_text(
        self,
        title: str,
        message: str,
    ) -> dict:
        """Send a free-text alert (not tied to a specific scan)."""
        if not self.is_configured:
            return {"status": "skipped", "reason": "no channels configured"}

        results = {}
        all_ok = True
        for ch in self._channels:
            channel_name = ch.__class__.__name__.replace("Channel", "").lower()
            ok = ch.send(title, message)
            results[channel_name] = "ok" if ok else "failed"
            if not ok:
                all_ok = False

        return {"status": "sent" if all_ok else "partial", "channels": results}

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

    def _build_title(self, repo_url: str, mr_id: Optional[int], mr_title: str) -> str:
        repo_name = repo_url.split("/")[-1].replace(".git", "") if repo_url else "unknown"
        if mr_id:
            return f"[PR-CodeGuard] {repo_name} !{mr_id} - 安全告警"
        return f"[PR-CodeGuard] {repo_name} - 安全告警"

    @staticmethod
    def _build_message(
        findings: list[Finding],
        repo_url: str,
        mr_id: Optional[int],
        mr_title: str,
        source_branch: str,
        target_branch: str,
        author: str,
    ) -> str:
        lines = []
        lines.append("## PR-CodeGuard 安全扫描告警")
        lines.append("")
        lines.append(f"- **仓库**: {repo_url or '-'}")
        if mr_id:
            lines.append(f"- **MR**: !{mr_id} - {mr_title or '-'}")
        if source_branch:
            lines.append(f"- **分支**: {source_branch} → {target_branch}")
        if author:
            lines.append(f"- **作者**: {author}")
        lines.append(f"- **严重问题**: {sum(1 for f in findings if _severity_index(f.severity.lower()) >= 3)} 个")
        lines.append(f"- **总问题数**: {len(findings)} 个")
        lines.append("")

        # List critical findings
        critical = [f for f in findings if _severity_index(f.severity.lower()) >= 3]
        if critical:
            lines.append("### 严重问题列表")
            lines.append("")
            for i, f in enumerate(critical[:10], 1):
                lines.append(f"{i}. **[{f.severity.upper()}]** {f.message[:120]}")
                lines.append(f"   - 文件: {f.file_path}:{f.line or '?'}")
                if f.rule_id:
                    lines.append(f"   - 规则: {f.rule_id}")
                if f.recommendation:
                    lines.append(f"   - 建议: {f.recommendation[:200]}")
                lines.append("")

        if len(critical) > 10:
            lines.append(f"... 及另外 {len(critical) - 10} 个严重问题")

        lines.append("---")
        lines.append(f"*PR-CodeGuard Agent · {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        return "\n".join(lines)
