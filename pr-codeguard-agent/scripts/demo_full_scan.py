"""
Full Demo: Run Trivy scan on test repo + post result to GitLab MR comment.

This demonstrates the complete PR-CodeGuard pipeline:
  1. Clone repo (via GitPython)
  2. Run Trivy scanner (vuln + secret + misconfig)
  3. Build review comment
  4. Post to GitLab MR
"""
import sys, os
sys.path.insert(0, r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent")

from app.models.task import ScanTask
from app.services.orchestrator import Orchestrator
from app.services.comment_builder import CommentBuilder
from app.services.gitlab_client import GitLabClient
from app.engine.trivy_scanner import TrivyScanner, _find_trivy

import asyncio
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("demo")

REPO_URL = "http://localhost/root/trivy-test-vuln-app.git"
MR_ID = 1
SOURCE_BRANCH = "feature/add-vulnerable-module"
TARGET_BRANCH = "main"

async def main():
    # ── 1. Scan via Orchestrator (full pipeline) ──
    print("\n" + "="*70)
    print("PHASE 1: Trivy Scan via Orchestrator")
    print("="*70)

    task = ScanTask(id="demo-final-001", repo_url=REPO_URL, mr_id=MR_ID, status="pending")
    orchestrator = Orchestrator()
    print(f"Engines: {list(orchestrator._engines.keys())}")

    result = await orchestrator.run_scan(
        task=task,
        source_branch=SOURCE_BRANCH,
        target_branch=TARGET_BRANCH,
        ai_enabled=False,
        tf_change_detection=False,
    )

    print(f"\nScan Status: {result.status}")
    print(f"Total Findings: {len(result.findings)}")
    print(f"Error: {result.error_message or 'none'}")

    # ── 2. Summary ──
    print("\n" + "="*70)
    print("PHASE 2: Results Summary")
    print("="*70)

    from collections import Counter
    if result.findings:
        sev = Counter(f.severity for f in result.findings)
        eng = Counter(f.engine for f in result.findings)
        print(f"Severity: {dict(sev)}")
        print(f"Engine:   {dict(eng)}")

        for f in result.findings:
            print(f"\n  [{f.severity.upper():8}] {f.rule_id}")
            print(f"  File:    {f.file_path}")
            print(f"  Message: {f.message[:100]}")
    else:
        print("No findings detected.")

    # ── 3. Post Comment to GitLab MR ──
    print("\n" + "="*70)
    print("PHASE 3: Posting Comment to GitLab MR !1")
    print("="*70)

    if result.findings:
        try:
            # Build comment using the CommentBuilder
            from app.services.gitlab_client import GitLabClient
            gc = GitLabClient()
            mr_changes = gc.get_mr_changes(REPO_URL, MR_ID)
            diff_stats = None
            if "diff_stats" in mr_changes:
                diff_stats = mr_changes.get("diff_stats")

            builder = CommentBuilder()
            comment = builder.build_review(result.findings, diff_stats=diff_stats)

            if comment:
                print(f"\nComment length: {len(comment)} chars")
                print("--- Comment Preview ---")
                print(comment[:1000])
                print("... (truncated)")

                # Clean up old bot comments and post new one
                gc.cleanup_bot_comments(REPO_URL, MR_ID)
                gc.post_comment(REPO_URL, MR_ID, comment)
                print("\n[OK] Comment posted to GitLab MR !1")
                print(f"URL: http://localhost/root/trivy-test-vuln-app/-/merge_requests/1")
        except Exception as e:
            print(f"\n[FAIL] Failed to post comment: {e}")
    else:
        print("No findings, skipping comment.")

    print("\n" + "="*70)
    print("DEMO COMPLETE")
    print("="*70)

if __name__ == "__main__":
    asyncio.run(main())
