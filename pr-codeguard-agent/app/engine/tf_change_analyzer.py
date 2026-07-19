"""Terraform change risk analyzer.

Parses MR diffs for .tf files and identifies resource-level changes.
Assigns risk levels based on change type + resource type.

Risk levels:
  🔴 critical - Deletion of critical resources (S3, RDS, IAM, KMS, etc.)
  🟠 major    - Deletion of moderate resources (VPC, SG, ECS, etc.)
  🟡 minor    - Deletion of low-risk resources / risky attribute changes
  🟢 info     - New resources or harmless changes
"""

import re
import logging
from typing import Optional

from app.models.finding import Finding

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Risk rules: resource deletion = severity mapping
# ---------------------------------------------------------------------------

# Resources whose deletion is critical
CRITICAL_DELETIONS = {
    "aws_s3_bucket", "aws_s3_bucket_object", "aws_s3_bucket_acl",
    "aws_s3_bucket_policy", "aws_s3_bucket_public_access_block",
    "aws_db_instance", "aws_rds_cluster", "aws_rds_cluster_instance",
    "aws_iam_role", "aws_iam_policy", "aws_iam_user", "aws_iam_group",
    "aws_kms_key", "aws_kms_alias",
    "aws_dynamodb_table",
    "aws_lb", "aws_alb", "aws_elb", "aws_lb_target_group",
    "aws_lambda_function", "aws_lambda_permission",
    "aws_elasticache_cluster", "aws_elasticache_replication_group",
    "aws_sqs_queue", "aws_sns_topic",
    "aws_eks_cluster", "aws_ecs_cluster",
}

# Resources whose deletion is major risk
MAJOR_DELETIONS = {
    "aws_vpc", "aws_subnet", "aws_route_table", "aws_internet_gateway",
    "aws_nat_gateway", "aws_eip", "aws_vpc_peering_connection",
    "aws_security_group",
    "aws_ecs_service", "aws_ecr_repository",
    "aws_cloudfront_distribution", "aws_acm_certificate",
    "aws_api_gateway_rest_api",
    "aws_efs_file_system",
    "aws_elasticsearch_domain", "aws_opensearch_domain",
    "aws_msk_cluster",
    "aws_docdb_cluster", "aws_neptune_cluster",
    "aws_redshift_cluster",
}

# Resources whose deletion is minor risk
MINOR_DELETIONS = {
    "aws_instance", "aws_launch_template", "aws_autoscaling_group",
    "aws_cloudwatch_metric_alarm", "aws_cloudwatch_log_group",
    "aws_route53_record", "aws_route53_zone",
    "aws_ecs_task_definition",
    "aws_iam_policy_attachment", "aws_iam_role_policy_attachment",
    "aws_lb_listener", "aws_lb_listener_rule",
    "aws_security_group_rule",
}

# All known AWS resource types (for detection)
_ALL_RESOURCE_TYPES = CRITICAL_DELETIONS | MAJOR_DELETIONS | MINOR_DELETIONS

# ---------------------------------------------------------------------------
# Diff parsing
# ---------------------------------------------------------------------------

# Pattern to match terraform resource declarations
_RESOURCE_PATTERN = re.compile(
    r'\bresource\s+"([^"]+)"\s+"([^"]+)"',
)

# Pattern to match data source declarations
_DATA_PATTERN = re.compile(
    r'\bdata\s+"([^"]+)"\s+"([^"]+)"',
)

# Pattern to match module declarations
_MODULE_PATTERN = re.compile(
    r'\bmodule\s+"([^"]+)"',
)

# Pattern to match terraform resource destruction (from comments or plan)
_DESTROY_PATTERN = re.compile(
    r'#\s*terraform\s+destroy|#\s*destroy|force_destroy\s*=\s*true',
    re.IGNORECASE,
)


def _classify_resource(resource_type: str) -> tuple[str, str]:
    """Classify a resource type into (severity, category).

    Returns:
        (severity_level, category_name): e.g. ("critical", "Storage")
    """
    if resource_type in CRITICAL_DELETIONS:
        return "critical", _get_category(resource_type)
    if resource_type in MAJOR_DELETIONS:
        return "major", _get_category(resource_type)
    if resource_type in MINOR_DELETIONS:
        return "minor", _get_category(resource_type)
    return "info", "Other"


_CATEGORY_MAP = {
    "aws_s3": "Storage",
    "aws_db_": "Database",
    "aws_rds": "Database",
    "aws_iam": "IAM",
    "aws_kms": "Encryption",
    "aws_dynamo": "Database",
    "aws_lambda": "Compute",
    "aws_ecs": "Container",
    "aws_ecr": "Container",
    "aws_eks": "Container",
    "aws_elasticache": "Database",
    "aws_sqs": "Messaging",
    "aws_sns": "Messaging",
    "aws_vpc": "Network",
    "aws_subnet": "Network",
    "aws_route_table": "Network",
    "aws_internet_gateway": "Network",
    "aws_nat": "Network",
    "aws_eip": "Network",
    "aws_security_group": "Network",
    "aws_alb": "Network",
    "aws_elb": "Network",
    "aws_lb_": "Network",
    "aws_cloudfront": "CDN",
    "aws_acm": "Certificate",
    "aws_api_gateway": "API",
    "aws_instance": "Compute",
    "aws_autoscaling": "Compute",
    "aws_cloudwatch": "Monitoring",
    "aws_route53": "DNS",
    "aws_efs": "Storage",
    "aws_redshift": "Database",
    "aws_docdb": "Database",
}


def _get_category(resource_type: str) -> str:
    for prefix, cat in _CATEGORY_MAP.items():
        if resource_type.startswith(prefix):
            return cat
    return "Other"


def _is_tf_file(file_path: str) -> bool:
    return file_path.endswith(".tf") and not file_path.startswith(".")


def _parse_diff_lines(diff_text: str) -> list[tuple[str, str, int]]:
    """Parse a unified diff for terraform files.

    Returns list of (operation, line_content, line_number) where
    operation is "+" (added), "-" (removed), or None for context.
    """
    lines = diff_text.split("\n")
    results = []
    # Track line numbers within the diff (approximate)
    add_line = 0
    rem_line = 0

    in_hunk = False
    for line in lines:
        if line.startswith("@@"):
            # Extract the new file start line from hunk header
            # @@ -old_start,count +new_start,count @@
            match = re.search(r'\+\d+', line)
            if match:
                add_line = int(match.group()[1:])
            in_hunk = True
            continue

        if not in_hunk:
            continue

        if line.startswith("+++") or line.startswith("---"):
            continue

        if line.startswith("+"):
            results.append(("+", line[1:], add_line))
            add_line += 1
        elif line.startswith("-"):
            results.append(("-", line[1:], rem_line or add_line))
            rem_line += 1
        else:
            add_line += 1
            rem_line += 1

    return results


def _extract_resources_from_diff(
    parsed_lines: list[tuple[str, str, int]],
) -> tuple[list[dict], list[dict]]:
    """Extract added and removed resources from parsed diff lines.

    Returns:
        (added_resources, removed_resources)
        Each resource: {"type": str, "name": str, "line": int}
    """
    added = []
    removed = []

    for op, content, line_num in parsed_lines:
        match = _RESOURCE_PATTERN.search(content)
        if match:
            res_type = match.group(1)
            res_name = match.group(2)
            if op == "+":
                added.append({"type": res_type, "name": res_name, "line": line_num})
            elif op == "-":
                removed.append({"type": res_type, "name": res_name, "line": line_num})

    return added, removed


# ---------------------------------------------------------------------------
# Main analyzer
# ---------------------------------------------------------------------------


class TfChangeAnalyzer:
    """Analyze Terraform diffs and produce risk-graded findings."""

    def __init__(self):
        pass

    def analyze(self, file_diffs: list[dict]) -> list[Finding]:
        """Analyze raw diffs from an MR and return change risk findings.

        Args:
            file_diffs: List of {"file_path", "diff", "new_file", "deleted_file"}.

        Returns:
            List of Finding objects with engine="tf_change".
        """
        findings: list[Finding] = []

        # Filter to .tf files
        tf_diffs = [d for d in file_diffs if _is_tf_file(d.get("file_path", ""))]
        if not tf_diffs:
            return findings

        for fd in tf_diffs:
            file_path = fd.get("file_path", "")
            diff_text = fd.get("diff", "")
            is_new = fd.get("new_file", False)
            is_deleted = fd.get("deleted_file", False)

            if not diff_text and not is_deleted:
                continue

            parsed = _parse_diff_lines(diff_text)
            added, removed = _extract_resources_from_diff(parsed)

            # --- Added resources (low risk by default) ---
            for res in added:
                sev, cat = _classify_resource(res["type"])
                # Creation is never critical
                if sev in ("critical", "major"):
                    sev = "minor"

                findings.append(Finding(
                    engine="tf_change",
                    severity=sev,
                    file_path=file_path,
                    line=res["line"],
                    message=f"新建 Terraform 资源: {res['type']}.{res['name']}",
                    code_snippet=f'resource "{res["type"]}" "{res["name"]}"',
                    rule_id=f"tf_change::create::{res['type']}",
                    recommendation=f"确认 {res['type']}.{res['name']} 的配置符合预期",
                ))

            # --- Removed resources (risk depends on type) ---
            for res in removed:
                sev, cat = _classify_resource(res["type"])
                risk_labels = {
                    "critical": "高危",
                    "major": "中危",
                    "minor": "低危",
                    "info": "信息",
                }

                findings.append(Finding(
                    engine="tf_change",
                    severity=sev,
                    file_path=file_path,
                    line=res["line"],
                    message=f"[{risk_labels.get(sev, '未知')}] 删除 {cat} 资源: {res['type']}.{res['name']}",
                    code_snippet=f'resource "{res["type"]}" "{res["name"]}"',
                    rule_id=f"tf_change::delete::{res['type']}",
                    recommendation=self._build_recommendation(res["type"], res["name"]),
                ))

        return findings

    @staticmethod
    def _build_recommendation(resource_type: str, resource_name: str) -> str:
        if resource_type in CRITICAL_DELETIONS:
            return (
                f"删除 {resource_type}.{resource_name} 可能导致数据丢失或服务中断。"
                "请确认: 1) 已备份数据 2) 已确认无依赖 3) 已通知相关团队"
            )
        if resource_type in MAJOR_DELETIONS:
            return (
                f"删除 {resource_type}.{resource_name} 可能影响相关服务。"
                "请确认: 1) 无其他资源依赖 2) 已评估影响范围"
            )
        return f"请确认 {resource_type}.{resource_name} 的删除是否在计划中"
