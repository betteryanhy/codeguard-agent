from app.models.finding import Finding


class CommentBuilder:
    """Build formatted Markdown review comments from scan findings."""

    SEVERITY_ORDER = ["blocker", "critical", "major", "minor", "info"]

    SEVERITY_LABELS = {
        "blocker": "[BLOCKER]",
        "critical": "[CRITICAL]",
        "major": "[MAJOR]",
        "minor": "[MINOR]",
        "info": "[INFO]",
    }

    def build_review(self, findings: list[Finding]) -> str:
        """Build a complete MR review comment body."""
        if not findings:
            return "**PR-CodeGuard Review**\n\nNo issues found. Looks good!"

        has_ai = any(f.ai_explanation for f in findings)

        # Group findings by severity
        grouped: dict[str, list[Finding]] = {s: [] for s in self.SEVERITY_ORDER}
        for f in findings:
            grouped.get(f.severity, grouped["info"]).append(f)

        lines = ["**PR-CodeGuard 代码审查报告**\n"]

        if has_ai:
            lines.append("> 每条问题已由 AI 生成简明解释，帮助快速理解与修复\n")

        for severity in self.SEVERITY_ORDER:
            items = grouped[severity]
            if not items:
                continue

            label = self.SEVERITY_LABELS.get(severity, severity.upper())
            lines.append(f"### {label} ({len(items)})")
            lines.append("")

            for f in items:
                location = f"`{f.file_path}`"
                if f.line:
                    location = f"`{f.file_path}:{f.line}`"

                lines.append(f"- **[{f.engine}]** {location}")
                lines.append(f"  > {f.message}")

                # AI explanation
                if f.ai_explanation:
                    lines.append(f"  > **AI 解释：** {f.ai_explanation}")

                if f.recommendation:
                    lines.append(f"  > **修复建议：** {f.recommendation}")
                if f.code_snippet:
                    safe_code = f.code_snippet.replace("`", "\\`")
                    lines.append(f"  ```text")
                    lines.append(f"  {safe_code[:200]}")
                    lines.append(f"  ```")
                lines.append("")

        lines.append("---")
        footer = f"*PR-CodeGuard Agent · {len(findings)} issues found*"
        if has_ai:
            footer += " · AI-powered explanation enabled"
        lines.append(footer)
        return "\n".join(lines)
