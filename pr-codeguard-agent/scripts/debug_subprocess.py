"""Debug: reproduce the exact subprocess call."""
import subprocess, json, os, sys

trivy = r"D:\Userfile\project\pr-codeguard\tools\trivy\trivy.exe"
cache = r"D:\Userfile\project\pr-codeguard\pr-codeguard-agent\data\trivy"
target = r"C:\Users\admin\AppData\Local\Temp\trivy-test-repo"

# Exact command the TrivyScanner generates
cmd = [
    trivy, "filesystem",
    "--format", "json",
    "--severity", "MEDIUM",
    "--scanners", "vuln,misconfig",
    "--quiet",
    "--cache-dir", cache,
    target,
]

print(f"Command: {' '.join(cmd)}")
print(f"cwd=None")

result = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=120)
print(f"RC={result.returncode} stdout={len(result.stdout)} stderr={result.stderr[:300]}")

# With cwd=target
result2 = subprocess.run(cmd, capture_output=True, encoding="utf-8", timeout=120, cwd=target)
print(f"RC={result2.returncode} stdout={len(result2.stdout)} stderr={result2.stderr[:300]}")

# Check JSON output
for rc, r, label in [(result.returncode, result, "no cwd"), (result2.returncode, result2, "cwd=target")]:
    if r.stdout.strip():
        try:
            data = json.loads(r.stdout)
            results = data.get("Results", [])
            total = sum(len(r.get("Vulnerabilities", [])) + len(r.get("Misconfigurations", [])) for r in results)
            print(f"  {label}: {total} findings (OK)")
        except Exception as e:
            print(f"  {label}: parse error: {e}")
    else:
        print(f"  {label}: no output. Stderr: {r.stderr[:200]}")
