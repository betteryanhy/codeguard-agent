"""Webhook endpoint for Terraform Plan JSON analysis.

Receives Terraform plan JSON from GitLab CI pipelines, analyzes resource
changes for risk assessment, and posts findings as MR comments.

Integration with GitLab CI:
  1. `.gitlab-ci.yml` runs `terraform plan -out=plan.tfplan`
  2. Then `terraform show -json plan.tfplan > plan.json`
  3. CI sends plan.json via curl to this endpoint
  4. Agent analyses and comments on the MR
"""

import json
import logging
from fastapi import APIRouter, Request, HTTPException

from app.engine.tf_plan_analyzer import TfPlanAnalyzer
from app.services.comment_builder import CommentBuilder
from app.services.gitlab_client import GitLabClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/webhook", tags=["tf_plan"])


@router.post("/tf-plan")
async def handle_tf_plan(request: Request):
    """Receive and analyze a Terraform plan JSON payload.

    Expected headers:
      - X-Project-Id: GitLab project ID (required)
      - X-MR-IID: Merge Request IID (required)

    Body: Full JSON output of `terraform show -json plan.tfplan`
    """
    # Validate headers
    project_id = request.headers.get("X-Project-Id")
    mr_iid = request.headers.get("X-MR-IID")

    if not project_id or not mr_iid:
        raise HTTPException(
            status_code=400,
            detail="Missing required headers: X-Project-Id, X-MR-IID",
        )

    try:
        project_id = int(project_id)
        mr_iid = int(mr_iid)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400,
            detail="X-Project-Id and X-MR-IID must be integers",
        )

    # Parse plan JSON from body
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON body: {e}",
        )

    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail="Body must be a JSON object (Terraform plan JSON)",
        )

    # Analyze the plan
    analyzer = TfPlanAnalyzer()
    findings = analyzer.analyze(body)

    logger.info(
        "TF Plan analysis for project %s MR !%s: %d findings",
        project_id, mr_iid, len(findings),
    )

    # Post findings as MR comment if findings exist
    if findings:
        try:
            gc = GitLabClient()
            comment_builder = CommentBuilder()
            comment_body = comment_builder.build_review(findings)
            gc.post_mr_comment(project_id, mr_iid, comment_body)
            logger.info(
                "TF Plan comment posted to project %s MR !%s",
                project_id, mr_iid,
            )
        except Exception as e:
            logger.error(
                "Failed to post TF Plan comment to project %s MR !%s: %s",
                project_id, mr_iid, e,
            )

    return {
        "status": "analyzed",
        "project_id": project_id,
        "mr_iid": mr_iid,
        "findings_count": len(findings),
        "findings": [
            {
                "severity": f.severity,
                "message": f.message,
                "file_path": f.file_path,
                "recommendation": f.recommendation,
                "rule_id": f.rule_id,
            }
            for f in findings
        ],
    }
