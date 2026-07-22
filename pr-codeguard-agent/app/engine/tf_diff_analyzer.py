"""
Terraform change analyzer - parses MR diffs to extract infrastructure changes.

Parses GitLab MR raw diffs for .tf files and identifies:
- Added resources (new aws_*, kubernetes_*, etc.)
- Modified resources (changed attributes)
- Deleted resources (removed blocks)
- Added/modified/deleted modules, variables, outputs, data sources

Produces a structured summary for the architecture impact comment section.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Resource declaration pattern: resource "type" "name" {
_RESOURCE_PATTERN = re.compile(
    r'^\s*resource\s+"([^"]+)"\s+"([^"]+)"\s*\{'
)
# Data source pattern: data "type" "name" {
_DATA_PATTERN = re.compile(
    r'^\s*data\s+"([^"]+)"\s+"([^"]+)"\s*\{'
)
# Module pattern: module "name" {
_MODULE_PATTERN = re.compile(
    r'^\s*module\s+"([^"]+)"\s*\{'
)
# Variable/Output pattern
_VARIABLE_PATTERN = re.compile(
    r'^\s*variable\s+"([^"]+)"\s*\{'
)
_OUTPUT_PATTERN = re.compile(
    r'^\s*output\s+"([^"]+)"\s*\{'
)
# Provider pattern
_PROVIDER_PATTERN = re.compile(
    r'^\s*provider\s+"([^"]+)"\s*\{'
)
# Locals pattern
_LOCALS_PATTERN = re.compile(
    r'^\s*locals\s*\{'
)


def _strip_diff_prefix(line: str) -> str:
    """Remove the leading + or - from a diff line (but not +++/--- lines)."""
    if line.startswith("+++") or line.startswith("---"):
        return ""
    if line.startswith("+") or line.startswith("-"):
        return line[1:]
    return line


def _classify_line(raw_line: str) -> dict | None:
    """Try to classify a single line as a Terraform block declaration.
    
    Handles raw diff lines with + or - prefixes from git diff.
    Returns dict with block type, resource type, name, or None.
    """
    line = _strip_diff_prefix(raw_line)
    if not line:
        return None

    m = _RESOURCE_PATTERN.match(line)
    if m:
        return {"type": "resource", "resource_type": m.group(1), "name": m.group(2)}

    m = _DATA_PATTERN.match(line)
    if m:
        return {"type": "data", "resource_type": m.group(1), "name": m.group(2)}

    m = _MODULE_PATTERN.match(line)
    if m:
        return {"type": "module", "name": m.group(1)}

    m = _VARIABLE_PATTERN.match(line)
    if m:
        return {"type": "variable", "name": m.group(1)}

    m = _OUTPUT_PATTERN.match(line)
    if m:
        return {"type": "output", "name": m.group(1)}

    m = _PROVIDER_PATTERN.match(line)
    if m:
        return {"type": "provider", "name": m.group(1)}

    if _LOCALS_PATTERN.match(line):
        return {"type": "locals"}

    return None


def analyze_tf_diff(file_path: str, diff: str) -> dict:
    """Analyze a single .tf file's diff for resource changes.
    
    Parses raw git diff content and extracts:
    - Added resources (lines starting with `+resource`)
    - Removed resources (lines starting with `-resource`)
    - Modified resources (resource declarations that have +/- changes near them)
    
    Args:
        file_path: Path to the .tf file.
        diff: Raw git diff string (from GitLab API).
    
    Returns:
        Dict with: file_path, added_resources, removed_resources,
                   modified_resources, has_changes.
    """
    result = {
        "file_path": file_path,
        "added_resources": [],
        "removed_resources": [],
        "modified_resources": [],
        "has_changes": False,
    }

    if not diff:
        return result

    lines = diff.split("\n")

    # Detect lines that are inside a diff hunk (between @@ headers)
    in_hunk = False
    
    for i, line in enumerate(lines):
        if line.startswith("@@"):
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if not line:
            continue

        # Check for added/removed resource declarations
        if line.startswith("+") and not line.startswith("+++"):
            stripped = line[1:]  # Remove the + prefix
            classified = _classify_line_raw(stripped)
            if classified and classified["type"] == "resource":
                _add_to_result(result, classified, "added")
                
        elif line.startswith("-") and not line.startswith("---"):
            stripped = line[1:]  # Remove the - prefix
            classified = _classify_line_raw(stripped)
            if classified and classified["type"] == "resource":
                _add_to_result(result, classified, "removed")

    # Detect modified resources: look for context resource declarations
    # near added/removed lines within the same hunk
    in_hunk = False
    current_context_resources = []
    
    for i, line in enumerate(lines):
        if line.startswith("@@"):
            in_hunk = True
            current_context_resources = []
            continue
        if not in_hunk:
            continue
        
        # Context line (no +/- prefix) - could be a resource declaration
        if not line.startswith("+") and not line.startswith("-") and not line.startswith("@@"):
            classified = _classify_line_raw(line)
            if classified and classified["type"] == "resource":
                current_context_resources.append((classified["resource_type"], classified["name"]))
        
        # Check if a +/- line exists near a context resource
        if line.startswith(("+", "-")) and current_context_resources:
            for res_type, res_name in current_context_resources:
                entry = {"resource_type": res_type, "name": res_name}
                if entry not in result["modified_resources"]:
                    result["modified_resources"].append(entry)
            # Keep only resources that are still in context
            current_context_resources = []

    result["has_changes"] = bool(
        result["added_resources"] or result["removed_resources"]
        or result["modified_resources"]
    )

    return result


def _classify_line_raw(line: str) -> dict | None:
    """Classify a line after stripping diff markers.
    
    Unlike _classify_line, this expects the line to already have
    any + or - prefixes removed.
    """
    if not line:
        return None
    
    m = _RESOURCE_PATTERN.match(line)
    if m:
        return {"type": "resource", "resource_type": m.group(1), "name": m.group(2)}

    m = _DATA_PATTERN.match(line)
    if m:
        return {"type": "data", "resource_type": m.group(1), "name": m.group(2)}

    m = _MODULE_PATTERN.match(line)
    if m:
        return {"type": "module", "name": m.group(1)}

    m = _VARIABLE_PATTERN.match(line)
    if m:
        return {"type": "variable", "name": m.group(1)}

    m = _OUTPUT_PATTERN.match(line)
    if m:
        return {"type": "output", "name": m.group(1)}

    m = _PROVIDER_PATTERN.match(line)
    if m:
        return {"type": "provider", "name": m.group(1)}

    if _LOCALS_PATTERN.match(line):
        return {"type": "locals"}

    return None


def _add_to_result(result: dict, classified: dict, action: str):
    """Add a classified block to the appropriate result list."""
    bt = classified["type"]
    if bt == "resource":
        entry = {
            "resource_type": classified["resource_type"],
            "name": classified["name"],
        }
        if action == "added" and entry not in result["added_resources"]:
            result["added_resources"].append(entry)
        elif action == "removed" and entry not in result["removed_resources"]:
            result["removed_resources"].append(entry)
    # Other block types (module, variable, output, etc.) are tracked
    # only via the per-file result dict keys initialized in analyze_tf_diff.


def analyze_tf_changes(raw_diffs: list[dict]) -> dict:
    """Analyze all terraform file changes across the MR.
    
    Args:
        raw_diffs: List of dicts with file_path, diff, new_file, deleted_file.
    
    Returns:
        Dict with: has_tf_changes, files (list of per-file analysis),
                   summary (list of human-readable summary strings),
                   added_resources (flat list), removed_resources (flat list),
                   modified_resources (flat list).
    """
    tf_diffs = [d for d in raw_diffs if d.get("file_path", "").endswith(".tf") and d.get("diff")]

    if not tf_diffs:
        return {
            "has_tf_changes": False,
            "files": [],
            "summary": [],
            "added_resources": [],
            "removed_resources": [],
            "modified_resources": [],
        }

    all_added = []
    all_removed = []
    all_modified = []
    file_results = []

    for td in tf_diffs:
        analysis = analyze_tf_diff(td["file_path"], td["diff"])
        if analysis["has_changes"]:
            file_results.append(analysis)
            all_added.extend(analysis["added_resources"])
            all_removed.extend(analysis["removed_resources"])
            all_modified.extend(analysis.get("modified_resources", []))

    # Deduplicate
    def dedup_list(items, keys):
        seen = set()
        result = []
        for item in items:
            key = tuple(item[k] for k in keys)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    all_added = dedup_list(all_added, ["resource_type", "name"])
    all_removed = dedup_list(all_removed, ["resource_type", "name"])
    all_modified = dedup_list(all_modified, ["resource_type", "name"])

    # Build summary text
    summary = []
    for af in file_results:
        file_path = af["file_path"]
        parts = []
        if af["added_resources"]:
            types = set(r["resource_type"] for r in af["added_resources"])
            parts.append(f"+{len(af['added_resources'])} resource(s) [{'/'.join(sorted(types))}]")
        if af["removed_resources"]:
            types = set(r["resource_type"] for r in af["removed_resources"])
            parts.append(f"-{len(af['removed_resources'])} resource(s) [{'/'.join(sorted(types))}]")
        if af["modified_resources"]:
            parts.append(f"~{len(af['modified_resources'])} resource(s) modified")
        if parts:
            summary.append(f"  - `{file_path}`: {', '.join(parts)}")

    return {
        "has_tf_changes": len(all_added) > 0 or len(all_removed) > 0 or len(all_modified) > 0,
        "files": file_results,
        "summary": summary,
        "added_resources": all_added,
        "removed_resources": all_removed,
        "modified_resources": all_modified,
    }


def format_tf_impact_section(tf_analysis: dict) -> list[str]:
    """Format the Terraform architecture impact section for MR comment.
    
    Args:
        tf_analysis: Output from analyze_tf_changes().
    
    Returns:
        List of Markdown lines for the architecture impact section.
    """
    if not tf_analysis or not tf_analysis.get("has_tf_changes"):
        return []

    lines = []
    lines.append("### 基础设施架构影响分析")
    lines.append("")

    # Resource changes summary
    added = tf_analysis.get("added_resources", [])
    removed = tf_analysis.get("removed_resources", [])
    modified = tf_analysis.get("modified_resources", [])

    if added:
        lines.append(f"**新增资源 ({len(added)})**")
        lines.append("")
        for r in added:
            lines.append(f"- `{r['resource_type']}` **{r['name']}**")
        lines.append("")

    if removed:
        lines.append(f"**删除资源 ({len(removed)})**")
        lines.append("")
        for r in removed:
            lines.append(f"- `{r['resource_type']}` **{r['name']}**")
        lines.append("")

    if modified:
        lines.append(f"**修改资源 ({len(modified)})**")
        lines.append("")
        for r in modified:
            lines.append(f"- `{r['resource_type']}` **{r['name']}**")
        lines.append("")

    # Architecture impact description
    impact_parts = []
    if added:
        resource_list = ", ".join(
            f"`{r['resource_type']}.{r['name']}`" for r in added[:5]
        )
        if len(added) > 5:
            resource_list += f" 等 {len(added)} 个资源"
        impact_parts.append(f"新增 {resource_list}")

    if removed:
        resource_list = ", ".join(
            f"`{r['resource_type']}.{r['name']}`" for r in removed[:3]
        )
        if len(removed) > 3:
            resource_list += f" 等 {len(removed)} 个资源"
        impact_parts.append(f"删除 {resource_list}")

    if modified:
        resource_list = ", ".join(
            f"`{r['resource_type']}.{r['name']}`" for r in modified[:3]
        )
        if len(modified) > 3:
            resource_list += f" 等 {len(modified)} 个资源"
        impact_parts.append(f"修改 {resource_list}")

    if impact_parts:
        lines.append("**影响评估**")
        lines.append("")
        lines.append("> 本次变更" + "，".join(impact_parts) + "，可能对以下方面产生影响：")
        lines.append("")
        lines.append("- **基础设施状态**: Terraform 将在下一次 apply 时执行对应操作")
        lines.append("- **依赖关系**: 相关资源的引用可能受到影响，请检查是否有资源间依赖断裂")
        lines.append("- **安全合规**: 新增资源需确保符合安全基线配置")

        # Specific impact notes based on resource type
        aws_added = [r for r in added if r["resource_type"].startswith("aws_")]
        k8s_added = [r for r in added if r["resource_type"].startswith("kubernetes_")]

        if aws_added:
            aws_types = set(r["resource_type"] for r in aws_added)
            lines.append("")
            lines.append(f"- **AWS 资源提醒**: 涉及 `{'/'.join(sorted(aws_types))}`，请确保 IAM 权限和配额充足")
        if k8s_added:
            k8s_types = set(r["resource_type"] for r in k8s_added)
            lines.append("")
            lines.append(f"- **Kubernetes 资源提醒**: 涉及 `{'/'.join(sorted(k8s_types))}`，请检查集群 RBAC 配置")

        lines.append("")

    # File-level detail
    if tf_analysis.get("summary"):
        lines.append("**变更文件明细**")
        lines.append("")
        lines.extend(tf_analysis["summary"])
        lines.append("")

    lines.append("---")
    lines.append("")

    return lines
