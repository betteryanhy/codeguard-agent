"""Debug Trivy integration: test scanner directly."""
import sys
sys.path.insert(0, r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent")

# Force the trivy path check
import os
os.environ["TRIVY_PATH"] = r"D:\Userfile\project\pr-codeguard\tools\trivy"

from app.engine.trivy_scanner import TrivyScanner, _find_trivy

print(f"Trivy found at: {_find_trivy()}")
print(f"Trivy.exe exists: {os.path.isfile(r'D:\Userfile\project\pr-codeguard\tools\trivy\trivy.exe')}")

scanner = TrivyScanner(
    scanners=("vuln", "secret", "misconfig"),
    severity_threshold="MEDIUM",
    cache_dir=r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent\data\trivy",
    offline=True,
    timeout=120,
)

print(f"Scanner name: {scanner.name}")
print(f"Cache dir: {scanner._cache_dir}")
print(f"Cache dir exists: {os.path.isdir(scanner._cache_dir)}")

repo_path = r"C:\Users\admin\AppData\Local\Temp\trivy-test-repo"
print(f"\nScanning: {repo_path}")
print(f"Repo exists: {os.path.isdir(repo_path)}")

findings = scanner.analyze(repo_path, diff_files=None)
print(f"\nResults: {len(findings)} findings")
for f in findings:
    print(f"  [{f.severity}] {f.engine}: {f.rule_id} - {f.message[:80]}")
