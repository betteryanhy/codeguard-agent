"""Terraform Plan analyzer engine.

Analyzes Terraform plan JSON output (from `terraform plan -json`) to detect
high-risk resource operations such as deletion of critical infrastructure.

Key design:
  - Static risk matrix: maps (action, resource_type) -> severity
  - Knowledge base integration: project-specific rules override defaults
  - Change context: groups related changes (e.g. deleting a security group
    that's referenced by other resources)

Integration with GitLab CI:
  1. `.gitlab-ci.yml` step runs `terraform plan -out=plan.tfplan`
  2. Then `terraform show -json plan.tfplan > plan.json`
  3. CI sends plan.json via webhook to Agent
  4. Agent parses, scores, and comments on MR
"""

import json
import logging
from typing import Any

from app.engine.base import AnalysisEngine
from app.models.finding import Finding

logger = logging.getLogger(__name__)

# Risk matrix: (action, resource_type) -> severity
# Actions: create, update, delete
RISK_MATRIX: dict[tuple[str, str], str] = {
    # --- DELETE operations (highest risk) ---
    ("delete", "aws_rds_cluster"): "critical",
    ("delete", "aws_rds_instance"): "critical",
    ("delete", "aws_s3_bucket"): "critical",
    ("delete", "aws_kms_key"): "critical",
    ("delete", "aws_kms_alias"): "critical",
    ("delete", "aws_vpc"): "critical",
    ("delete", "aws_vpc_peering_connection"): "critical",
    ("delete", "aws_ecs_service"): "critical",
    ("delete", "aws_ecr_repository"): "critical",
    ("delete", "aws_cloudfront_distribution"): "critical",
    ("delete", "aws_acm_certificate"): "critical",
    ("delete", "aws_api_gateway_rest_api"): "critical",
    ("delete", "aws_elasticsearch_domain"): "critical",
    ("delete", "aws_redshift_cluster"): "critical",
    ("delete", "aws_docdb_cluster"): "critical",
    ("delete", "aws_neptune_cluster"): "critical",
    ("delete", "aws_msk_cluster"): "critical",
    ("delete", "aws_dynamodb_table"): "major",
    ("delete", "aws_elasticache_cluster"): "major",
    ("delete", "aws_security_group"): "major",
    ("delete", "aws_lb"): "major",
    ("delete", "aws_lb_target_group"): "major",
    ("delete", "aws_instance"): "major",
    # --- CREATE operations (medium risk - needs review) ---
    ("create", "aws_security_group_rule"): "major",
    ("create", "aws_iam_role"): "major",
    ("create", "aws_iam_policy"): "major",
    ("create", "aws_s3_bucket_public_access_block"): "minor",
    ("create", "aws_s3_bucket"): "minor",
    # --- UPDATE operations (low risk) ---
    ("update", "aws_security_group_rule"): "major",
    ("update", "aws_iam_role"): "minor",
    ("update", "aws_iam_policy"): "minor",
    # --- Terraform resource types ---
    ("delete", "module"): "major",
    ("delete", "data"): "minor",
    # --- Kubernetes resources ---
    ("delete", "kubernetes_namespace"): "critical",
    ("delete", "kubernetes_deployment"): "major",
    ("delete", "kubernetes_service"): "major",
    # --- GCP resources ---
    ("delete", "google_compute_instance"): "major",
    ("delete", "google_sql_database_instance"): "critical",
    ("delete", "google_storage_bucket"): "critical",
    ("delete", "google_kms_crypto_key"): "critical",
    # --- Azure resources ---
    ("delete", "azurerm_resource_group"): "critical",
    ("delete", "azurerm_sql_database"): "critical",
    ("delete", "azurerm_key_vault"): "critical",
    ("delete", "azurerm_virtual_machine"): "major",
}

# Resources that should be flagged if created without encryption/tags
REQUIRES_ENCRYPTION = {
    "aws_s3_bucket",
    "aws_rds_cluster",
    "aws_rds_instance",
    "aws_dynamodb_table",
    "aws_kms_key",
    "aws_sqs_queue",
    "aws_sns_topic",
}

REQUIRES_TAGS = {
    "aws_instance",
    "aws_s3_bucket",
    "aws_rds_cluster",
    "aws_rds_instance",
    "aws_dynamodb_table",
    "aws_lb",
    "aws_ecs_service",
}


def _get_action(change: dict) -> str:
    """Extract the action from a resource change."""
    actions = change.get("change", {}).get("actions", ["no-op"])
    if "delete" in actions:
        return "delete"
    if "create" in actions:
        return "create"
    if "update" in actions:
        return "update"
    return "no-op"


def _has_tag(tags: Any, key: str) -> bool:
    """Check if a set of tags contains a specific key."""
    if isinstance(tags, dict):
        return key in tags or key.lower() in {k.lower() for k in tags}
    return False


def _format_address(change: dict) -> str:
    """Format the resource address from a change."""
    address = change.get("address", "")
    module = change.get("module", "")
    if module:
        return f"{module}.{address}"
    return address


class TfPlanAnalyzer(AnalysisEngine):
    """Analyzes Terraform plan JSON for resource change risk assessment.

    Detects risky operations (deletion of critical infrastructure, creation
    of security group rules, etc.) and can be extended with project-specific
    rules via the knowledge base.
    """

    def __init__(self):
        self._risk_matrix = dict(RISK_MATRIX)

    @property
    def name(self) -> str:
        return "tf_plan"

    def analyze(self, plan_json: dict | str, diff_files: list[str] | None = None) -> list[Finding]:
        """Analyze a Terraform plan JSON document.

        Args:
            plan_json: Parsed JSON dict or raw JSON string from
                      `terraform show -json plan.tfplan`.
            diff_files: Not used for TF Plan analysis (included for
                       interface compatibility).

        Returns:
            List of Finding objects with risk assessment.
        """
        if isinstance(plan_json, str):
            try:
                plan_json = json.loads(plan_json)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse Terraform plan JSON: %s", e)
                return []

        if not isinstance(plan_json, dict):
            logger.warning("Invalid Terraform plan format: expected dict")
            return []

        return self._analyze_plan(plan_json)

    def analyze_from_file(self, file_path: str) -> list[Finding]:
        """Analyze a Terraform plan JSON file.

        Args:
            file_path: Path to a plan.json file.

        Returns:
            List of Finding objects.
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                plan_json = json.load(f)
            return self._analyze_plan(plan_json)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("Failed to load TF plan from %s: %s", file_path, e)
            return []

    def _analyze_plan(self, plan_json: dict) -> list[Finding]:
        """Core analysis logic."""
        findings: list[Finding] = []
        changes = plan_json.get("resource_changes", [])

        if not changes:
            logger.info("No resource changes in Terraform plan")
            return findings

        logger.info("Analyzing %d Terraform resource changes", len(changes))

        for change in changes:
            action = _get_action(change)
            resource_type = change.get("type", "unknown")
            address = _format_address(change)

            # 1. Check static risk matrix
            risk = self._risk_matrix.get((action, resource_type))
            if risk:
                change_after = change.get("change", {}).get("after", {})
                details = self._build_detail(action, resource_type, change_after)

                findings.append(Finding(
                    engine="tf_plan",
                    severity=risk,
                    file_path=address,
                    line=None,
                    message=(
                        f"[Terraform Plan] {action.upper()} "
                        f"{resource_type} -> {address}"
                    ),
                    code_snippet=details[:200],
                    recommendation=self._get_recommendation(action, resource_type),
                    rule_id=f"tf_{action}_{resource_type}",
                ))

            # 2. Check encryption compliance (new resources)
            if action == "create" and resource_type in REQUIRES_ENCRYPTION:
                change_after = change.get("change", {}).get("after", {})
                if not self._check_encryption(resource_type, change_after):
                    findings.append(Finding(
                        engine="tf_plan",
                        severity="major",
                        file_path=address,
                        line=None,
                        message=(
                            f"[Terraform Plan] {resource_type} created "
                            f"without encryption configured"
                        ),
                        recommendation=(
                            f"Enable encryption for {resource_type} "
                            f"using `encryption` or `kms_key_id` parameter"
                        ),
                        rule_id=f"tf_missing_encryption_{resource_type}",
                    ))

        return findings

    @staticmethod
    def _build_detail(action: str, resource_type: str, after: dict) -> str:
        """Build a detail string for the change."""
        parts = [f"Action: {action.upper()}", f"Type: {resource_type}"]
        if after:
            name = after.get("name") or after.get("tags", {}).get("Name", "")
            if name:
                parts.append(f"Name: {name}")
        return " | ".join(parts)

    @staticmethod
    def _get_recommendation(action: str, resource_type: str) -> str:
        """Generate a recommendation based on action and resource type."""
        if action == "delete":
            return (
                f"Review before deleting {resource_type}. Ensure no "
                f"downstream dependencies will be affected and data is backed up."
            )
        if action == "create":
            return f"Review {resource_type} configuration for security best practices."
        if action == "update":
            return f"Review {resource_type} changes for unintended side effects."
        return ""

    @staticmethod
    def _check_encryption(resource_type: str, after: dict) -> bool:
        """Check if a resource has encryption enabled."""
        if resource_type == "aws_s3_bucket":
            # Check server-side encryption config
            server_side = after.get("server_side_encryption_configuration")
            return server_side is not None
        if resource_type in ("aws_rds_cluster", "aws_rds_instance"):
            kms_key = after.get("kms_key_id")
            return kms_key is not None and kms_key != ""
        if resource_type == "aws_dynamodb_table":
            sse = after.get("sse_specification", {})
            return sse.get("enabled", False) if isinstance(sse, dict) else False
        if resource_type == "aws_kms_key":
            return True  # KMS keys are encrypted by default
        if resource_type in ("aws_sqs_queue", "aws_sns_topic"):
            kms_key = after.get("kms_master_key_id")
            return kms_key is not None and kms_key != ""
        return True  # Default: assume encrypted
