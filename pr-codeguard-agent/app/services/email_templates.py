"""HTML email template engine for daily digest reports.

Renders structured daily report data into styled HTML emails
suitable for sending via SMTP.
"""

import logging

logger = logging.getLogger(__name__)

SEVERITY_COLORS = {
    "critical": "#d32f2f",
    "major": "#e65100",
    "minor": "#1565c0",
    "info": "#2e7d32",
    "blocker": "#b71c1c",
}

STATE_COLORS = {
    "merged": "#1b5e20",
    "opened": "#e65100",
    "closed": "#616161",
    "locked": "#c62828",
}


class EmailTemplates:
    """HTML email template renderer."""

    # ------------------------------------------------------------------
    # Daily Report HTML Template
    # ------------------------------------------------------------------

    DAILY_REPORT_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light">
  <style>
    /* Reset */
    body, table, td, p, h1, h2 {{ margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; margin: 0; padding: 0; background: #f0f2f5; -webkit-font-smoothing: antialiased; }}
    .container {{ max-width: 600px; margin: 0 auto; padding: 16px 8px; }}
    /* Header */
    .header {{ background: linear-gradient(135deg, #1565c0 0%, #1e88e5 100%); color: white; padding: 32px 28px; border-radius: 12px 12px 0 0; }}
    .header h1 {{ margin: 0; font-size: 22px; font-weight: 700; letter-spacing: 0.5px; }}
    .header p {{ margin: 8px 0 0; opacity: 0.9; font-size: 14px; }}
    .header .badge {{ display: inline-block; margin-top: 12px; padding: 4px 12px; background: rgba(255,255,255,0.2); border-radius: 20px; font-size: 12px; font-weight: 500; }}
    /* Body card */
    .body {{ padding: 28px; background: white; border: 1px solid #e0e0e0; border-top: none; border-radius: 0 0 12px 12px; }}
    /* Section */
    .section {{ margin-bottom: 28px; }}
    .section:last-child {{ margin-bottom: 0; }}
    .section h2 {{ font-size: 15px; font-weight: 700; color: #1a1a1a; margin: 0 0 14px; padding-bottom: 10px; border-bottom: 2px solid #1565c0; text-transform: uppercase; letter-spacing: 0.3px; }}
    /* Summary grid */
    .summary-grid {{ display: table; width: 100%; border-collapse: collapse; }}
    .summary-grid .cell {{ display: table-cell; padding: 14px 8px; text-align: center; background: #fafafa; border: 1px solid #e8e8e8; width: 25%; }}
    .summary-grid .cell .num {{ font-size: 28px; font-weight: 800; line-height: 1.2; }}
    .summary-grid .cell .label {{ font-size: 10px; color: #888; margin-top: 2px; text-transform: uppercase; letter-spacing: 0.5px; }}
    /* Tables */
    table.data-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    table.data-table th {{ background: #f5f7fa; text-align: left; padding: 10px 12px; font-weight: 700; color: #444; font-size: 12px; text-transform: uppercase; letter-spacing: 0.3px; border-bottom: 2px solid #e0e0e0; }}
    table.data-table td {{ padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }}
    table.data-table tr:last-child td {{ border-bottom: none; }}
    table.data-table tr:hover td {{ background: #f8f9ff; }}
    /* State badges */
    .state-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; color: white; }}
    /* Findings */
    .finding-item {{ padding: 12px 14px; margin-bottom: 8px; background: #fff8e1; border-left: 4px solid #e65100; border-radius: 6px; font-size: 13px; line-height: 1.5; }}
    .finding-item.critical {{ background: #ffebee; border-left-color: #d32f2f; }}
    .finding-item .sev-badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 10px; font-weight: 700; color: white; text-transform: uppercase; letter-spacing: 0.5px; margin-right: 8px; vertical-align: middle; }}
    .finding-item .finding-msg {{ vertical-align: middle; }}
    .finding-item .finding-file {{ display: block; margin-top: 6px; font-size: 11px; color: #999; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; }}
    /* Footer */
    .footer {{ text-align: center; padding: 20px 0 4px; font-size: 11px; color: #bbb; }}
    .footer a {{ color: #999; text-decoration: none; }}
    /* Divider */
    .divider {{ height: 1px; background: #e8e8e8; margin: 16px 0; }}
    /* Responsive */
    @media (max-width: 480px) {{
      .container {{ padding: 8px 4px; }}
      .header {{ padding: 24px 16px; }}
      .header h1 {{ font-size: 18px; }}
      .body {{ padding: 16px; }}
      .summary-grid .cell {{ display: block; width: 100%; box-sizing: border-box; }}
      table.data-table {{ font-size: 12px; }}
      table.data-table th, table.data-table td {{ padding: 8px 6px; }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>PR-CodeGuard 每日报告</h1>
      <p>{date} · 代码安全与开发活动概览</p>
      {header_badge}
    </div>
    <div class="body">
      <div class="section">
        <h2>扫描概览</h2>
        <div class="summary-grid">
          <div class="cell">
            <div class="num" style="color: {c_color};">{critical_count}</div>
            <div class="label">CRITICAL</div>
          </div>
          <div class="cell">
            <div class="num" style="color: {m_color};">{major_count}</div>
            <div class="label">MAJOR</div>
          </div>
          <div class="cell">
            <div class="num" style="color: {i_color};">{minor_count}</div>
            <div class="label">MINOR</div>
          </div>
          <div class="cell">
            <div class="num" style="color: #1565c0;">{scans_count}</div>
            <div class="label">扫描次数</div>
          </div>
        </div>
      </div>

      <div class="section">
        <h2>开发者活跃度</h2>
        {developer_html}
      </div>

      <div class="section">
        <h2>项目更新</h2>
        {project_updates_html}
      </div>

      <div class="section">
        <h2>高风险发现</h2>
        {top_findings_html}
      </div>

      <div class="section">
        <h2>仓库风险评估</h2>
        {repo_risk_html}
      </div>

      <div class="footer">
        <p>由 PR-CodeGuard Agent 自动生成 · {date}</p>
      </div>
    </div>
  </div>
</body>
</html>"""

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render_daily(self, data: dict) -> str:
        """Render daily digest data into HTML email.

        Args:
            data: Output from DailyDigest.generate().

        Returns:
            Complete HTML string for the email body.
        """
        scan_summary = data.get("scan_summary", {})
        by_severity = scan_summary.get("by_severity", {})
        dev_activity = data.get("developer_activity", [])
        project_updates = data.get("project_updates", [])
        top_findings = data.get("top_findings", [])
        per_repo_risk = data.get("per_repo_risk", [])

        critical_count = by_severity.get("critical", 0)
        major_count = by_severity.get("major", 0)
        minor_count = by_severity.get("minor", 0)

        # Optional header badge for critical findings
        badge = (
            f'<span class="badge">&#9888; {critical_count} 个高危发现</span>'
            if critical_count > 0
            else ""
        )

        # Risk color: highest among all repos
        risk_color = SEVERITY_COLORS.get("info", "#2e7d32")
        if critical_count > 0:
            risk_color = SEVERITY_COLORS.get("critical", "#d32f2f")
        elif major_count > 0:
            risk_color = SEVERITY_COLORS.get("major", "#e65100")

        return self.DAILY_REPORT_HTML.format(
            date=data.get("date", ""),
            header_badge=badge,
            c_color=SEVERITY_COLORS.get("critical", "#d32f2f"),
            m_color=SEVERITY_COLORS.get("major", "#e65100"),
            i_color=SEVERITY_COLORS.get("minor", "#1565c0"),
            critical_count=critical_count,
            major_count=major_count,
            minor_count=minor_count,
            scans_count=scan_summary.get("total_scans", 0),
            developer_html=self._render_developer_table(dev_activity),
            project_updates_html=self._render_project_updates(project_updates),
            top_findings_html=self._render_top_findings(top_findings),
            repo_risk_html=self._render_repo_risk_table(per_repo_risk),
        )

    def render_subject(self, data: dict) -> str:
        """Generate an email subject line."""
        scan_summary = data.get("scan_summary", {})
        by_severity = scan_summary.get("by_severity", {})
        critical = by_severity.get("critical", 0)
        total = scan_summary.get("total_findings", 0)

        parts = [f"PR-CodeGuard 每日报告 - {data.get('date', '')}"]
        if critical > 0:
            parts.append(f"[{critical} 个高危]")
        parts.append(f"共 {total} 个发现")
        return " · ".join(parts)

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    @staticmethod
    def _render_developer_table(dev_activity: list[dict]) -> str:
        """Render developer activity table HTML."""
        if not dev_activity:
            return "<p style='color: #999; font-size: 13px;'>今日暂无开发活动</p>"

        rows = []
        total_commits = 0
        total_mrs = 0
        for dev in dev_activity:
            commits = dev.get("commits", 0)
            mrs = dev.get("mrs", 0)
            changes = f"+{dev.get('additions', 0)}/-{dev.get('deletions', 0)}"
            rows.append(
                f"<tr>"
                f"<td><strong>{dev.get('name', '')}</strong></td>"
                f"<td style='text-align: center;'>{commits}</td>"
                f"<td style='text-align: center;'>{mrs}</td>"
                f"<td style='text-align: center; font-family: monospace;'>{changes}</td>"
                f"</tr>"
            )
            total_commits += commits
            total_mrs += mrs

        return (
            "<table class='data-table'>"
            "<tr><th>开发者</th><th style='text-align: center;'>提交</th>"
            "<th style='text-align: center;'>MR</th>"
            "<th style='text-align: center;'>+/- 行</th></tr>"
            + "".join(rows) +
            "<tr style='background: #f5f7fa; font-weight: 700;'>"
            f"<td>合计 ({len(dev_activity)} 人)</td>"
            f"<td style='text-align: center;'>{total_commits}</td>"
            f"<td style='text-align: center;'>{total_mrs}</td>"
            f"<td></td></tr>"
            "</table>"
        )

    @staticmethod
    def _render_project_updates(updates: list[dict]) -> str:
        """Render project updates HTML."""
        if not updates:
            return "<p style='color: #999; font-size: 13px;'>今日无项目更新</p>"

        items = []
        for u in updates:
            detail = u.get("detail", "")
            title = u.get("title", "")
            state = u.get("state", "")
            state_color = STATE_COLORS.get(state, "#757575")
            items.append(
                f"<tr>"
                f"<td><strong>{detail}</strong></td>"
                f"<td>{title[:60]}</td>"
                f"<td><span class='state-badge' style='background: {state_color};'>{state}</span></td>"
                f"</tr>"
            )

        return (
            "<table class='data-table'>"
            "<tr><th>MR</th><th>标题</th><th>状态</th></tr>"
            + "".join(items) +
            "</table>"
        )

    @staticmethod
    def _render_top_findings(findings: list[dict]) -> str:
        """Render top critical findings HTML."""
        if not findings:
            return "<p style='color: #999; font-size: 13px;'>今日无高危发现</p>"

        items = []
        for f in findings:
            sev = f.get("severity", "major")
            color = SEVERITY_COLORS.get(sev, "#e65100")
            cls = "critical" if sev in ("critical", "blocker") else ""
            msg = f.get("message", "")[:100]
            file_path = f.get("file", "")

            items.append(
                f"<div class='finding-item {cls}'>"
                f"<span class='sev-badge' style='background: {color};'>{sev.upper()}</span>"
                f"<span class='finding-msg'>{msg}</span>"
                f"<span class='finding-file'>{file_path}</span>"
                f"</div>"
            )

        return "".join(items)

    @staticmethod
    def _render_repo_risk_table(repo_risks: list[dict]) -> str:
        """Render per-repository risk assessment table."""
        if not repo_risks:
            return "<p style='color: #999; font-size: 13px;'>暂无仓库风险评估数据</p>"

        RISK_COLORS = {
            "CRITICAL": "#d32f2f",
            "MAJOR": "#e65100",
            "MINOR": "#1565c0",
            "SAFE": "#2e7d32",
        }

        rows = []
        for r in repo_risks:
            rl = r.get("risk_level", "SAFE")
            rc = RISK_COLORS.get(rl, "#757575")
            sev = r.get("by_severity", {})
            engines = r.get("by_engine", {})
            engine_str = ", ".join(f"{k}={v}" for k, v in sorted(engines.items()))

            rows.append(
                f"<tr>"
                f"<td><strong>{r.get('repo', '')}</strong></td>"
                f"<td><span class='state-badge' style='background: {rc};'>{rl}</span></td>"
                f"<td style='text-align: center;'>{r.get('total_findings', 0)}</td>"
                f"<td style='text-align: center; font-size: 11px;'>C:{sev.get('critical',0)} M:{sev.get('major',0)} m:{sev.get('minor',0)}</td>"
                f"<td style='font-size: 11px; color: #888;'>{engine_str}</td>"
                f"</tr>"
            )

        return (
            "<table class='data-table'>"
            "<tr><th>仓库</th><th>风险等级</th><th style='text-align: center;'>发现数</th>"
            "<th style='text-align: center;'>严重度分布</th><th>引擎</th></tr>"
            + "".join(rows) +
            "</table>"
        )
