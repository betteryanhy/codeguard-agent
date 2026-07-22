"""Debug: check clone + trivy step by step."""
import sys, os, subprocess, json
sys.path.insert(0, r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent")

from app.services.repo_manager import RepoManager

# 1. Clone manually
rm = RepoManager()
print(f"Base dir: {rm.base_dir}")

repo_url = "http://localhost/root/trivy-test-vuln-app.git"
branch = "feature/add-vulnerable-module"
mr_id = 1

clone_dir = rm.clone_repo(repo_url, branch, mr_id)
print(f"\nClone dir: {clone_dir}")
print(f"Clone exists: {os.path.isdir(clone_dir)}")

# List files
files = os.listdir(clone_dir)
print(f"Files: {files}")

# 2. Run trivy directly on clone dir
trivy_path = r"D:\Userfile\project\pr-codeguard\tools\trivy\trivy.exe"
cache_dir = r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent\data\trivy"

cmd = [
    trivy_path, "filesystem",
    "--format", "json",
    "--severity", "MEDIUM",
    "--scanners", "vuln,secret,misconfig",
    "--quiet", "--skip-db-update",
    "--cache-dir", cache_dir,
    clone_dir,
]

print(f"\nRunning: {' '.join(cmd)}")
result = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=120)
print(f"Return code: {result.returncode}")
print(f"Stdout len: {len(result.stdout)}")
print(f"Stderr: {result.stderr[:300] if result.stderr else 'none'}")

# Parse
if result.stdout.strip():
    data = json.loads(result.stdout)
    results = data.get("Results", [])
    total = sum(
        len(r.get("Vulnerabilities", [])) + 
        len(r.get("Misconfigurations", [])) + 
        len(r.get("Secrets", []))
        for r in results
    )
    print(f"\nTotal issues found: {total}")
    for r in results:
        t = r.get("Target", "")
        v = len(r.get("Vulnerabilities", []))
        m = len(r.get("Misconfigurations", []))
        s = len(r.get("Secrets", []))
        print(f"  {t}: vuln={v} misconfig={m} secret={s}")

# Cleanup
rm.cleanup(clone_dir)
print(f"\nClone dir cleaned up: {not os.path.isdir(clone_dir)}")
