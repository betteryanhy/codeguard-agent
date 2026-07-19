"""Report mailer - generates and sends HTML-formatted reports via email.

Usage:
    mailer = ReportMailer()
    mailer.send_daily_report("2026-07-18")
"""

import json
import smtplib
import logging
from datetime import datetime, timedelta, date
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def _parse_dt(val):
    """Parse datetime from string or return as-is."""
    if isinstance(val, str):
        return datetime.fromisoformat(val.replace("Z", "+00:00")).replace(tzinfo=None)
    return val


def _kv(k, v, unit="") -> str:
    return f'<tr><td style="padding:6px 12px;color:#666;white-space:nowrap">{k}</td><td style="padding:6px 12px;font-weight:600">{v}{unit}</td></tr>'


class ReportMailer:
    """Generate and send HTML-formatted report emails."""

    def __init__(self):
        self._kb = None

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------

    def _get_kb(self):
        if self._kb is None:
            from app.main import knowledge_base
            self._kb = knowledge_base
        return self._kb

    def _get_daily_data(self, report_date: date) -> dict:
        """Collect all data for a daily report from the knowledge base."""
        kb = self._get_kb()
        if not kb:
            return {"error": "Knowledge base not available"}

        day_start = datetime(report_date.year, report_date.month, report_date.day)
        day_end = day_start + timedelta(days=1)

        # Get MR records
        try:
            mr_records = kb.sqlite.get_mr_records_by_date(day_start, day_end)
        except AttributeError:
            mr_records = []

        # Get commits
        all_commits = []
        for mr in mr_records:
            try:
                commits = kb.get_commits_by_mr(mr.repo_url, mr.mr_id)
                all_commits.extend(commits)
            except Exception:
                pass

        # Developer stats
        dev_stats: dict[str, dict] = {}
        for c in all_commits:
            name = c.author_name or "unknown"
            if name not in dev_stats:
                dev_stats[name] = {
                    "author_name": name,
                    "commits": 0,
                    "additions": 0,
                    "deletions": 0,
                    "files_changed": 0,
                    "repos": set(),
                }
            dev_stats[name]["commits"] += 1
            dev_stats[name]["additions"] += c.additions
            dev_stats[name]["deletions"] += c.deletions
            dev_stats[name]["files_changed"] += c.files_changed
            dev_stats[name]["repos"].add(c.repo_url)

        # Repo stats
        repo_stats: dict[str, dict] = {}
        total_risks = 0
        all_findings = []

        for mr in mr_records:
            repo = mr.repo_url
            if repo not in repo_stats:
                repo_stats[repo] = {
                    "repo_url": repo,
                    "mr_count": 0,
                    "total_additions": 0,
                    "total_deletions": 0,
                    "developers": set(),
                    "findings_count": 0,
                }
            repo_stats[repo]["mr_count"] += 1
            repo_stats[repo]["developers"].add(mr.author or "unknown")

            if mr.risks:
                try:
                    risks = json.loads(mr.risks)
                    total_risks += len(risks)
                    repo_stats[repo]["findings_count"] += len(risks)
                    for r in risks:
                        all_findings.append({
                            "repo": repo,
                            "mr_id": mr.mr_id,
                            "severity": r.get("severity", ""),
                            "message": r.get("message", ""),
                        })
                except (json.JSONDecodeError, TypeError):
                    pass

        # Sum additions/deletions from commits per repo
        for c in all_commits:
            if c.repo_url in repo_stats:
                repo_stats[c.repo_url]["total_additions"] += c.additions
                repo_stats[c.repo_url]["total_deletions"] += c.deletions

        # Count merged vs opened
        merged_count = sum(
            1 for r in mr_records
            if r.merged_at and day_start <= _parse_dt(r.merged_at) < day_end
        )

        return {
            "date": report_date.isoformat(),
            "summary": {
                "total_mrs": len(mr_records),
                "mr_merged": merged_count,
                "mr_opened": len(mr_records) - merged_count,
                "total_commits": len(all_commits),
                "total_additions": sum(s["additions"] for s in dev_stats.values()),
                "total_deletions": sum(s["deletions"] for s in dev_stats.values()),
                "total_developers": len(dev_stats),
                "total_repos": len(repo_stats),
                "total_risks": total_risks,
            },
            "developers": sorted(dev_stats.values(), key=lambda x: -x["commits"]),
            "repositories": sorted(repo_stats.values(), key=lambda x: -x["mr_count"]),
            "mr_records": [
                {
                    "mr_id": r.mr_id,
                    "repo": r.repo_url.split("/")[-1].replace(".git", "") if r.repo_url else "",
                    "title": r.mr_title or "",
                    "author": r.author or "",
                    "source_branch": r.source_branch or "",
                    "target_branch": r.target_branch or "",
                    "summary": (r.summary or "")[:200],
                    "is_merged": r.merged_at is not None and day_start <= _parse_dt(r.merged_at) < day_end,
                }
                for r in sorted(mr_records, key=lambda x: x.created_at or datetime.min)
            ],
            "findings": all_findings,
            "weekly_trends": self._get_weekly_trends(),
        }

    def _get_weekly_trends(self) -> list[dict]:
        """Get weekly trends for the last 4 weeks to include in report."""
        try:
            from app.services.trend_analyzer import TrendAnalyzer
            analyzer = TrendAnalyzer()
            return analyzer.get_weekly_trends(4)
        except Exception as e:
            logger.debug("Failed to get weekly trends: %s", e)
            return []

    # ------------------------------------------------------------------
    # HTML template
    # ------------------------------------------------------------------

    def _build_html(self, data: dict) -> str:
        """Build an HTML email for a daily report."""
        s = data.get("summary", {})
        devs = data.get("developers", [])
        repos = data.get("repositories", [])
        mrs = data.get("mr_records", [])
        findings = data.get("findings", [])

        # --- Header ---
        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; color: #333; margin: 0; padding: 0; background: #f5f5f5; }}
.container {{ max-width: 680px; margin: 0 auto; padding: 20px; }}
.header {{ background: linear-gradient(135deg, #1a73e8, #0d47a1); color: white; padding: 30px; border-radius: 8px 8px 0 0; }}
.header h1 {{ margin: 0; font-size: 22px; }}
.header p {{ margin: 8px 0 0; opacity: 0.85; font-size: 14px; }}
.section {{ background: white; padding: 20px 24px; border-bottom: 1px solid #eee; }}
.section:last-child {{ border-radius: 0 0 8px 8px; }}
.section h2 {{ font-size: 16px; margin: 0 0 12px; color: #1a73e8; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ text-align: left; padding: 8px 6px; font-size: 12px; color: #888; border-bottom: 1px solid #eee; text-transform: uppercase; }}
td {{ padding: 8px 6px; font-size: 13px; border-bottom: 1px solid #f5f5f5; }}
tr:last-child td {{ border-bottom: none; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
.badge-green {{ background: #e6f4ea; color: #1e7e34; }}
.badge-blue {{ background: #e8f0fe; color: #1a73e8; }}
.badge-red {{ background: #fce8e6; color: #c5221f; }}
.badge-orange {{ background: #fef7e0; color: #e37400; }}
.stat-grid {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 16px; }}
.stat-card {{ background: #f8f9fa; border-radius: 8px; padding: 14px 18px; flex: 1; min-width: 100px; text-align: center; }}
.stat-card .num {{ font-size: 28px; font-weight: 700; color: #1a73e8; }}
.stat-card .label {{ font-size: 11px; color: #666; margin-top: 2px; }}
.footer {{ text-align: center; padding: 20px; font-size: 11px; color: #999; }}
</style></head>
<body>
<div class="container">
<div class="header">
<h1>📋 PR-CodeGuard 日报</h1>
<p>{data.get('date', '')} · 自动生成报告</p>
</div>
"""

        # --- Summary Stats ---
        html += '<div class="section"><div class="stat-grid">'
        html += f'<div class="stat-card"><div class="num">{s.get("total_mrs", 0)}</div><div class="label">MR 总数</div></div>'
        html += f'<div class="stat-card"><div class="num" style="color:#1e7e34">{s.get("mr_merged", 0)}</div><div class="label">已合并</div></div>'
        html += f'<div class="stat-card"><div class="num" style="color:#e37400">{s.get("mr_opened", 0)}</div><div class="label">开启中</div></div>'
        html += f'<div class="stat-card"><div class="num">{s.get("total_commits", 0)}</div><div class="label">提交数</div></div>'
        html += f'<div class="stat-card"><div class="num">+{s.get("total_additions", 0)}</div><div class="label">新增行</div></div>'
        html += f'<div class="stat-card"><div class="num" style="color:#c5221f">-{s.get("total_deletions", 0)}</div><div class="label">删除行</div></div>'
        html += f'<div class="stat-card"><div class="num">{s.get("total_developers", 0)}</div><div class="label">开发者</div></div>'
        html += f'<div class="stat-card"><div class="num" style="color:#c5221f">{s.get("total_risks", 0)}</div><div class="label">安全问题</div></div>'
        html += '</div></div>'

        # --- MR Details ---
        if mrs:
            html += '<div class="section"><h2>📌 MR 活动详情</h2>'
            html += '<table><tr><th>ID</th><th>仓库</th><th>标题</th><th>作者</th><th>状态</th></tr>'
            for mr in mrs[:20]:
                status_badge = '<span class="badge badge-green">已合并</span>' if mr.get("is_merged") else '<span class="badge badge-blue">进行中</span>'
                repo_short = mr.get("repo", "")[:20]
                title_short = mr.get("title", "")[:40]
                html += f'<tr><td>!{mr.get("mr_id", "")}</td><td>{repo_short}</td><td>{title_short}</td><td>{mr.get("author", "")}</td><td>{status_badge}</td></tr>'
            html += '</table></div>'

        # --- Developer Activity ---
        if devs:
            html += '<div class="section"><h2>👨‍💻 开发者贡献</h2>'
            html += '<table><tr><th>开发者</th><th>提交</th><th>新增</th><th>删除</th><th>文件</th></tr>'
            for d in devs:
                html += f'<tr><td><strong>{d.get("author_name", "")}</strong></td><td>{d.get("commits", 0)}</td><td style="color:#1e7e34">+{d.get("additions", 0)}</td><td style="color:#c5221f">-{d.get("deletions", 0)}</td><td>{d.get("files_changed", 0)}</td></tr>'
            html += '</table></div>'

        # --- Repository Summary ---
        if repos:
            html += '<div class="section"><h2>📦 仓库概览</h2>'
            html += '<table><tr><th>仓库</th><th>MR</th><th>新增</th><th>删除</th><th>开发者</th><th>安全问题</th></tr>'
            for r in repos:
                repo_name = r.get("repo_url", "").split("/")[-1].replace(".git", "") or r.get("repo_url", "")
                dev_count = len(r.get("developers", []))
                risk_count = r.get("findings_count", 0)
                risk_display = f'<span style="color:#c5221f">{risk_count}</span>' if risk_count > 0 else str(risk_count)
                html += f'<tr><td>{repo_name}</td><td>{r.get("mr_count", 0)}</td><td style="color:#1e7e34">+{r.get("total_additions", 0)}</td><td style="color:#c5221f">-{r.get("total_deletions", 0)}</td><td>{dev_count}</td><td>{risk_display}</td></tr>'
            html += '</table></div>'

        # --- Security Findings ---
        if findings:
            critical = [f for f in findings if f.get("severity", "").lower() in ("critical", "blocker")]
            html += '<div class="section"><h2>🔒 安全问题通报</h2>'
            if critical:
                html += f'<p style="color:#c5221f">发现 {len(critical)} 个严重问题，请及时处理。</p>'
                html += '<table><tr><th>仓库</th><th>MR</th><th>级别</th><th>描述</th></tr>'
                for f in critical[:10]:
                    badge_cls = "badge-red" if f.get("severity", "").lower() == "blocker" else "badge-orange"
                    badge = f'<span class="badge {badge_cls}">{f.get("severity", "").upper()}</span>'
                    repo_short = f.get("repo", "").split("/")[-1].replace(".git", "")[:15] if f.get("repo") else ""
                    html += f'<tr><td>{repo_short}</td><td>!{f.get("mr_id", "")}</td><td>{badge}</td><td>{f.get("message", "")[:60]}</td></tr>'
                html += '</table>'
            else:
                html += '<p style="color:#1e7e34">✅ 本次扫描未发现严重安全问题。</p>'
            html += '</div>'

        # --- Trend section ---
        trends = data.get("weekly_trends", [])
        if len(trends) >= 2:
            html += '<div class="section"><h2>📈 近4周趋势概览</h2>'
            html += '<table><tr><th>周次</th><th>MR数</th><th>提交数</th><th>新增行</th><th>删除行</th><th>开发者</th><th>风险数</th><th>高危风险</th></tr>'
            for t in trends:
                html += (
                    f'<tr>'
                    f'<td>{t["period"]}</td>'
                    f'<td>{t["mr_count"]}</td>'
                    f'<td>{t["commit_count"]}</td>'
                    f'<td style="color:#1e7e34">+{t["additions"]}</td>'
                    f'<td style="color:#d32f2f">-{t["deletions"]}</td>'
                    f'<td>{t["developer_count"]}</td>'
                    f'<td>{t["risk_count"]}</td>'
                    f'<td>{t["critical_risk_count"]}</td>'
                    f'</tr>'
                )
            html += '</table></div>'

        # --- Footer ---
        html += f"""<div class="footer">
<p>PR-CodeGuard Agent · {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
此邮件由系统自动生成</p>
</div>
</div></body></html>"""

        return html

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    def send_daily_report(self, report_date: Optional[str] = None) -> dict:
        """Generate and send a daily report email.

        Args:
            report_date: Date string (YYYY-MM-DD). Defaults to today.

        Returns:
            Dict with send status.
        """
        if not settings.alert_smtp_host:
            return {"status": "error", "message": "SMTP not configured"}

        # Parse date
        if report_date:
            try:
                d = datetime.strptime(report_date, "%Y-%m-%d").date()
            except ValueError:
                return {"status": "error", "message": f"Invalid date: {report_date}"}
        else:
            d = date.today()

        # Collect data
        data = self._get_daily_data(d)
        if "error" in data:
            return {"status": "error", "message": data["error"]}

        # No data
        if data["summary"]["total_mrs"] == 0 and data["summary"]["total_commits"] == 0:
            subject = f"[PR-CodeGuard] {d.isoformat()} 日报 - 无活动记录"
            body = f"<p>{d.isoformat()} 日没有检测到任何代码活动。</p>"
        else:
            s = data["summary"]
            subject = f"[PR-CodeGuard] {d.isoformat()} 日报 - {s.get('total_mrs', 0)} MR / +{s.get('total_additions', 0)} -{s.get('total_deletions', 0)} 行"
            body = self._build_html(data)

        # Build email
        msg = MIMEMultipart()
        msg["From"] = settings.alert_email_from
        msg["To"] = ", ".join(settings.alert_email_to or [])
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html", "utf-8"))

        # Send
        try:
            with smtplib.SMTP(settings.alert_smtp_host, settings.alert_smtp_port, timeout=30) as server:
                if settings.alert_smtp_use_tls:
                    server.starttls()
                if settings.alert_smtp_user:
                    server.login(settings.alert_smtp_user, settings.alert_smtp_password)
                server.sendmail(settings.alert_email_from, settings.alert_email_to or [], msg.as_string())

            logger.info("Daily report sent: %s", subject)
            return {"status": "sent", "subject": subject, "date": d.isoformat()}
        except Exception as e:
            logger.warning("Failed to send daily report: %s", e)
            return {"status": "error", "message": str(e)}
