"""One-shot demo: scan local test repo + post result to GitLab MR."""
import sys, os
sys.path.insert(0, r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent")

from app.models.task import ScanTask
from app.services.orchestrator import Orchestrator
from app.engine.trivy_scanner import TrivyScanner, _find_trivy
import asyncio, logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

REPO_PATH = r"C:\Users\admin\AppData\Local\Temp\trivy-test-repo"

async def main():
    print("=" * 70)
    print("PHASE 1: Direct TrivyScanner on local repo")
    print("=" * 70)

    scanner = TrivyScanner(scanners=("vuln", "misconfig"), offline=False)
    scanner._cache_dir = r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent\data\trivy"
    findings = scanner.analyze(REPO_PATH)
    print(f"Direct Findings: {len(findings)}")

    for f in findings:
        print(f"  [{f.severity.upper():8}] {f.rule_id} - {f.message[:100]}")

    print("\n" + "=" * 70)
    print("PHASE 2: Orchestrator scan on local repo (via ScannerTool)")
    print("=" * 70)

    task = ScanTask(id="demo-local-002", repo_url=REPO_PATH, mr_id=1, status="pending")
    orchestrator = Orchestrator()

    # Monkey-patch clone to use local path
    original_clone = orchestrator.repo_manager.clone_repo
    orchestrator.repo_manager.clone_repo = lambda *a, **kw: REPO_PATH

    result = await orchestrator.run_scan(
        task=task, source_branch="feature", target_branch="main",
        ai_enabled=False, tf_change_detection=False,
    )

    print(f"\nOrchestrator Status: {result.status}")
    print(f"Orchestrator Findings: {len(result.findings)}")
    for f in result.findings:
        print(f"  [{f.severity.upper():8}] {f.rule_id} - {f.message[:100]}")

    print("\n" + "=" * 70)
    print("PHASE 3: Post comment to GitLab MR !1")
    print("=" * 70)

    if result.findings:
        from app.services.comment_builder import CommentBuilder
        from app.services.gitlab_client import GitLabClient

        builder = CommentBuilder()
        comment = builder.build_review(result.findings)

        if comment:
            print(f"\nComment length: {len(comment)} chars")
            print("--- Preview (first 500 chars) ---")
            print(comment[:500])

            gc = GitLabClient()
            gc.cleanup_bot_comments("http://localhost/root/trivy-test-vuln-app.git", 1)
            gc.post_comment("http://localhost/root/trivy-test-vuln-app.git", 1, comment)
            print("\n[OK] Comment posted!")
            print(f"URL: http://localhost/root/trivy-test-vuln-app/-/merge_requests/1")
    else:
        print("No findings to post")

    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
