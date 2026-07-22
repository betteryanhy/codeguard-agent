"""One-shot scan demo: run Trivy directly on the test repo."""
import sys
import asyncio
sys.path.insert(0, r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent")

from app.models.task import ScanTask
from app.services.orchestrator import Orchestrator

async def main():
    repo_url = "http://localhost/root/trivy-test-vuln-app.git"
    source_branch = "feature/add-vulnerable-module"
    target_branch = "main"
    mr_id = 1

    task = ScanTask(
        id="demo-scan-trivy-001",
        repo_url=repo_url,
        mr_id=mr_id,
        status="pending",
    )

    orchestrator = Orchestrator()
    print("Engines loaded:", list(orchestrator._engines.keys()))
    result = await orchestrator.run_scan(
        task=task,
        source_branch=source_branch,
        target_branch=target_branch,
        diff_files=None,
        enabled_engines=["trivy"],
        ai_enabled=False,
        tf_change_detection=False,
    )

    print(f"\n=== Scan Complete ===")
    print(f"Status: {result.status}")
    print(f"Total findings: {len(result.findings)}")
    print(f"Error: {result.error_message}")

    # Group by severity
    from collections import Counter
    sev_counts = Counter(f.severity for f in result.findings)
    print(f"Severity breakdown: {dict(sev_counts)}")

    # Print findings
    for f in result.findings:
        print(f"\n--- [{f.severity}] {f.engine} ---")
        print(f"  File: {f.file_path}")
        print(f"  Rule: {f.rule_id}")
        print(f"  Message: {f.message}")
        print(f"  Details: {f.details}")
        if f.line_numbers:
            print(f"  Lines: {f.line_numbers}")

if __name__ == "__main__":
    asyncio.run(main())
