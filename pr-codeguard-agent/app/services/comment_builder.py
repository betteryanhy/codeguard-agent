"""Build formatted Markdown review comments from scan findings."""

import re
from collections import defaultdict

from app.models.finding import Finding


class CommentBuilder:
    """Build formatted Markdown review comments from scan findings."""

    SEVERITY_ORDER = ["blocker", "critical", "major", "minor", "info"]

    SEVERITY_LABELS = {
        "blocker": "BLOCKER",
        "critical": "CRITICAL",
        "major": "MAJOR",
        "minor": "MINOR",
        "info": "INFO",
    }

    # Pattern to parse Trivy vuln messages:
    # "[go.mod] CVE-2023-26125: github.com/gin-gonic/gin v1.7.7 (fix: 1.9.0)"
    _VULN_MSG_RE = re.compile(
        r"\[(?P<file>[^\]]+)\]\s+"
        r"(?P<cve>CVE-\d+-\d+):\s+"
        r"(?P<package>\S+)\s+"
        r"(?P<version>\S+)"
        r"(?:\s+\(fix:\s*(?P<fix>\S+)\))?"
    )

    def build_review(
        self,
        findings: list[Finding],
        diff_stats: list[dict] | None = None,
        tf_analysis: dict | None = None,
    ) -> str:
        """Build a complete MR review comment body.

        Args:
            findings: List of scan findings.
            diff_stats: Optional list of file change stats
                (keys: file_path, additions, deletions, new_file, deleted_file).
            tf_analysis: Optional Terraform change analysis
                (from tf_diff_analyzer.analyze_tf_changes()).

        Returns:
            Formatted Markdown string for the MR comment.
        """
        if not findings and not tf_analysis:
            return "## PR-CodeGuard 审查报告\n\n未发现任何问题，审查通过。"

        has_ai = any(f.ai_explanation for f in findings)

        # Group findings by severity
        grouped: dict[str, list[Finding]] = {s: [] for s in self.SEVERITY_ORDER}
        for f in findings:
            grouped.get(f.severity, grouped["info"]).append(f)

        # Count by severity
        severity_counts = {}
        for f in findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

        blocker_count = severity_counts.get("blocker", 0)
        critical_count = severity_counts.get("critical", 0)
        high_risk_count = blocker_count + critical_count

        lines = []
        lines.append("## PR-CodeGuard 审查报告")
        lines.append("")

        # ── Section 1: Risk Evaluation ────────────────────────────
        lines.append("### 风险评价")
        lines.append("")

        # Severity table
        labels_row = []
        counts_row = []
        for s in self.SEVERITY_ORDER:
            cnt = severity_counts.get(s, 0)
            if cnt > 0 or s in ("critical", "blocker", "major"):
                labels_row.append(self.SEVERITY_LABELS.get(s, s.upper()))
                counts_row.append(str(cnt))
        if labels_row:
            lines.append("| " + " | ".join(labels_row) + " |")
            lines.append("|" + "|".join("---" for _ in labels_row) + "|")
            lines.append("| " + " | ".join(counts_row) + " |")
            lines.append("")

        # Overall risk rating
        if high_risk_count > 0:
            lines.append(
                f"> 存在 {high_risk_count} 个高危风险"
                f"（blocker={blocker_count}, critical={critical_count}），"
                f"建议修复后合并"
            )
        elif severity_counts.get("major", 0) > 0:
            lines.append(
                f"> 存在 {severity_counts['major']} 个中等级别风险，建议检查后合并"
            )
        else:
            lines.append("> 未发现明显风险")

        lines.append("")

        # ── Section 2: Component Summary (new) ────────────────────
        # Group trivy vuln findings by package for a clear summary
        vuln_packages = self._group_vulns_by_package(findings)
        if vuln_packages:
            lines.append("### 组件风险总览")
            lines.append("")
            lines.append(
                f"本次扫描发现 **{len(findings)} 个问题**，"
                f"涉及 **{len(vuln_packages)} 个组件**："
            )
            lines.append("")

            # Summary table
            lines.append("| 组件 | 漏洞数 | 最高严重度 | 关键建议 |")
            lines.append("|------|--------|-----------|---------|")
            for pkg_name, info in sorted(
                vuln_packages.items(),
                key=lambda x: max(self.SEVERITY_ORDER.index(s) for s in x[1]["severities"]),
            ):
                max_sev = max(info["severities"], key=lambda s: self.SEVERITY_ORDER.index(s))
                sev_label = self.SEVERITY_LABELS.get(max_sev, max_sev.upper())

                # Build concise suggestion
                fix_versions = [v for v in info["fix_versions"] if v]
                if fix_versions:
                    best_fix = max(fix_versions, key=lambda v: [int(x) for x in re.findall(r"\d+", v)] if re.findall(r"\d+", v) else [0])
                    suggestion = f"建议升级至 {best_fix}"
                else:
                    suggestion = "暂无修复版本，需评估"

                lines.append(f"| `{pkg_name}` | {info['count']} | {sev_label} | {suggestion} |")

            lines.append("")
            lines.append("")

        # ── Section 3: Change Overview ────────────────────────────
        if diff_stats:
            lines.append("### 变更概览")
            lines.append("")

            total_additions = sum(f.get("additions", 0) for f in diff_stats)
            total_deletions = sum(f.get("deletions", 0) for f in diff_stats)
            new_files = [f for f in diff_stats if f.get("new_file")]
            deleted_files = [f for f in diff_stats if f.get("deleted_file")]
            modified_files = [
                f for f in diff_stats
                if not f.get("new_file") and not f.get("deleted_file")
            ]

            if new_files:
                lines.append(f"- **新增 {len(new_files)} 个文件**")
                for f in new_files[:3]:
                    lines.append(f"  - `{f.get('file_path', '')}` (+{f.get('additions', 0)}行)")
                if len(new_files) > 3:
                    lines.append(f"  - ...及 {len(new_files) - 3} 个")

            if deleted_files:
                lines.append(f"- **删除 {len(deleted_files)} 个文件**")
                for f in deleted_files[:3]:
                    lines.append(f"  - `{f.get('file_path', '')}` (-{f.get('deletions', 0)}行)")

            if modified_files:
                lines.append(f"- **修改 {len(modified_files)} 个文件**")
                for f in modified_files[:3]:
                    delta = f.get('additions', 0) + f.get('deletions', 0)
                    lines.append(f"  - `{f.get('file_path', '')}` (+{f.get('additions', 0)}/-{f.get('deletions', 0)}行)")

            if total_additions + total_deletions > 0:
                lines.append(f"- **代码行数**: +{total_additions} / -{total_deletions} 行")

            lines.append("")

        # ── Section 4: Detailed Findings (grouped intelligently) ──
        lines.append("### 风险详情")
        lines.append("")

        if has_ai:
            lines.append("> 每条问题已由 AI 生成简明解释\n")

        for severity in self.SEVERITY_ORDER:
            items = grouped[severity]
            if not items:
                continue

            label = self.SEVERITY_LABELS.get(severity, severity.upper())
            prefix = "🔴 " if severity in ("blocker", "critical") else \
                     "🟡 " if severity == "major" else \
                     "🔵 " if severity == "minor" else ""

            lines.append(f"**{prefix}[{label}] ({len(items)} 个问题)**")
            lines.append("")

            # Split into trivy vuln (group by package) and others (flat list)
            trivy_vuln, others = self._split_trivy_vuln(items)

            # --- Trivy vuln findings: group by package ---
            if trivy_vuln:
                pkg_groups = self._group_vulns_by_package(trivy_vuln)
                for pkg_name in sorted(pkg_groups.keys()):
                    info = pkg_groups[pkg_name]
                    lines.append(f"  **📦 {pkg_name}** ({info['count']} 个漏洞)")
                    for f in info["findings"]:
                        parsed = self._parse_vuln_msg(f.message)
                        if parsed:
                            cve = parsed["cve"]
                            fix_info = f" → 修复版本: {parsed['fix']}" if parsed["fix"] else " ⚠ 暂无修复版本"
                            lines.append(f"    - `{cve}` {fix_info}")
                        else:
                            lines.append(f"    - {f.message[:120]}")
                    lines.append("")

            # --- Other findings (secrets, IaC, etc.): flat list ---
            for f in others:
                location = f"`{f.file_path}`"
                if f.line:
                    location = f"`{f.file_path}:{f.line}`"

                engine_label = {
                    "iac": "IaC",
                    "secrets": "Secrets",
                    "sast": "SAST",
                    "best_practice": "Best Practice",
                    "ai_review": "AI Review",
                }.get(f.engine, f.engine.upper())

                lines.append(f"- **[{engine_label}]** {location}")

                # For trivy findings not parsed as vuln, show shorter message
                if f.engine == "trivy":
                    lines.append(f"  - {self._shorten_message(f.message)}")
                else:
                    lines.append(f"  - {f.message}")

                if f.ai_explanation:
                    lines.append(f"  - **AI 解释**: {f.ai_explanation}")

                if f.recommendation:
                    lines.append(f"  - **建议**: {f.recommendation}")

                if f.code_snippet:
                    safe_code = f.code_snippet.replace("`", "\\`")
                    lines.append("  ```text")
                    lines.append(f"  {safe_code[:200]}")
                    lines.append("  ```")
                lines.append("")

        # ── Section 5: Terraform/Infrastructure Impact Analysis ────
        if tf_analysis:
            from app.engine.tf_diff_analyzer import format_tf_impact_section
            tf_lines = format_tf_impact_section(tf_analysis)
            if tf_lines:
                lines.extend(tf_lines)

        # Footer
        lines.append("---")
        footer_parts = [f"PR-CodeGuard Agent · 发现 {len(findings)} 个问题"]
        if has_ai:
            footer_parts.append("AI 智能分析已启用")
        if high_risk_count > 0:
            footer_parts.append(f"⚠ 建议优先处理 {high_risk_count} 个高危风险")
        if tf_analysis and tf_analysis.get("has_tf_changes"):
            footer_parts.append("🏗 基础设施变更已检测")
        lines.append(" · ".join(footer_parts))

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_vuln_msg(self, message: str) -> dict | None:
        """Parse a Trivy vulnerability message into structured fields."""
        m = self._VULN_MSG_RE.search(message)
        if not m:
            return None
        return {
            "file": m.group("file"),
            "cve": m.group("cve"),
            "package": m.group("package"),
            "version": m.group("version"),
            "fix": m.group("fix"),
        }

    def _shorten_message(self, message: str) -> str:
        """Shorten a Trivy message for compact display."""
        parsed = self._parse_vuln_msg(message)
        if parsed:
            parts = [parsed["cve"]]
            if parsed["fix"]:
                parts.append(f"建议升级至 {parsed['fix']}")
            else:
                parts.append("暂无修复版本")
            return " | ".join(parts)
        return message[:120]

    def _group_vulns_by_package(self, findings: list[Finding]) -> dict:
        """Group Trivy vulnerability findings by package name.

        Returns dict of:
            {package_name: {
                "count": int,
                "severities": set[str],
                "fix_versions": set[str],
                "findings": list[Finding],
            }}
        """
        packages: dict = {}

        for f in findings:
            if f.engine != "trivy":
                continue
            parsed = self._parse_vuln_msg(f.message)
            if not parsed:
                continue

            pkg_name = parsed["package"]
            if pkg_name not in packages:
                packages[pkg_name] = {
                    "count": 0,
                    "severities": set(),
                    "fix_versions": set(),
                    "findings": [],
                }

            packages[pkg_name]["count"] += 1
            packages[pkg_name]["severities"].add(f.severity)
            if parsed["fix"]:
                packages[pkg_name]["fix_versions"].add(parsed["fix"])
            packages[pkg_name]["findings"].append(f)

        return packages

    def _split_trivy_vuln(self, findings: list[Finding]) -> tuple[list[Finding], list[Finding]]:
        """Split findings into Trivy vuln findings (parseable) and others."""
        trivy_vuln = []
        others = []
        for f in findings:
            if f.engine == "trivy" and self._VULN_MSG_RE.search(f.message):
                trivy_vuln.append(f)
            else:
                others.append(f)
        return trivy_vuln, others
