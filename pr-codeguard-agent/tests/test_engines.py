import pytest
from app.engine.base import AnalysisEngine
from app.engine.secrets_scanner import SecretsScanner
from app.engine.sast_scanner import SastScanner
from app.engine.iac_scanner import IacScanner
from app.engine.best_practice import BestPracticeScanner


def test_engine_base_is_abstract():
    with pytest.raises(TypeError):
        AnalysisEngine()  # type: ignore


# === Secrets Scanner ===

def test_secrets_scanner_name():
    scanner = SecretsScanner()
    assert scanner.name == "secrets"


def test_secrets_scanner_analyze_empty_dir(tmp_path):
    scanner = SecretsScanner()
    results = scanner.analyze(str(tmp_path))
    assert isinstance(results, list)
    assert len(results) == 0


# === SAST Scanner ===

def test_sast_scanner_name():
    scanner = SastScanner()
    assert scanner.name == "sast"


def test_sast_scanner_analyze_empty_dir(tmp_path):
    scanner = SastScanner()
    results = scanner.analyze(str(tmp_path))
    assert isinstance(results, list)


# === IaC Scanner ===

def test_iac_scanner_name():
    scanner = IacScanner()
    assert scanner.name == "iac"


def test_iac_scanner_analyze_empty_dir(tmp_path):
    scanner = IacScanner()
    results = scanner.analyze(str(tmp_path))
    assert isinstance(results, list)


# === Best Practice Scanner ===

def test_best_practice_scanner_name():
    scanner = BestPracticeScanner()
    assert scanner.name == "best_practice"


def test_best_practice_detects_commented_secret(tmp_path):
    scanner = BestPracticeScanner()
    test_file = tmp_path / "config.py"
    test_file.write_text("# API_KEY=sk-1234567890\nprint('hello')")
    findings = scanner.analyze(str(tmp_path), diff_files=["config.py"])
    assert len(findings) >= 1
    assert findings[0].severity == "minor"


def test_best_practice_detects_todo_without_ticket(tmp_path):
    scanner = BestPracticeScanner()
    test_file = tmp_path / "app.py"
    test_file.write_text("# TODO: implement this later\n# FIXME: need to fix\n# TODO(PROJ-123): this one is ok\n")
    findings = scanner.analyze(str(tmp_path), diff_files=["app.py"])
    todo_findings = [f for f in findings if "TODO" in f.message]
    assert len(todo_findings) >= 1


def test_best_practice_ignore_dot_git(tmp_path):
    scanner = BestPracticeScanner()
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("secret=xyz")
    test_file = tmp_path / "app.py"
    test_file.write_text("print('hello')\n")
    findings = scanner.analyze(str(tmp_path))
    assert all(".git" not in f.file_path for f in findings)
