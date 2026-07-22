"""Debug: check trivy output directly."""
import subprocess, json

trivy = r"D:\Userfile\project\pr-codeguard\tools\trivy\trivy.exe"
cache = r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent\data\trivy"
target = r"C:\Users\admin\AppData\Local\Temp\trivy-test-repo"

cmd = [trivy, "filesystem", "--format", "json", "--severity", "MEDIUM",
       "--scanners", "vuln,misconfig", "--quiet", "--cache-dir", cache, target]

result = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=120)
print(f"RC={result.returncode}")
print(f"stdout ({len(result.stdout)} chars):")
print(result.stdout[:500])
print(f"\nstderr: {result.stderr[:200]}")

# Also try with --skip-db-update
cmd2 = cmd.copy()
cmd2.insert(cmd2.index("--quiet") + 1, "--skip-db-update")
result2 = subprocess.run(cmd2, capture_output=True, encoding="utf-8", timeout=120)
print(f"\nWith --skip-db-update:")
print(f"RC={result2.returncode}")
print(f"stdout ({len(result2.stdout)} chars):")
print(result2.stdout[:500])
print(f"\nstderr: {result2.stderr[:200]}")
