from app.services.comment_builder import CommentBuilder
from app.models.finding import Finding


def test_comment_builder_empty():
    builder = CommentBuilder()
    result = builder.build_review([])
    assert "No issues found" in result


def test_comment_builder_with_findings():
    builder = CommentBuilder()
    findings = [
        Finding(
            engine="secrets",
            severity="blocker",
            file_path="src/config.py",
            line=10,
            message="Hardcoded API key detected",
            recommendation="Use environment variables",
            code_snippet="API_KEY=sk-123",
        ),
        Finding(
            engine="best_practice",
            severity="info",
            file_path="src/app.py",
            line=5,
            message="TODO without ticket reference",
        ),
    ]
    result = builder.build_review(findings)
    assert "[BLOCKER]" in result
    assert "[INFO]" in result
    assert "Hardcoded API key" in result
    assert "TODO without ticket" in result
    assert "src/config.py" in result
    assert "src/app.py" in result


def test_comment_builder_grouping():
    """Verify findings are grouped by severity in order."""
    builder = CommentBuilder()
    findings = [
        Finding(engine="test", severity="info", file_path="a.py", message="info msg"),
        Finding(engine="test", severity="critical", file_path="b.py", message="critical msg"),
        Finding(engine="test", severity="blocker", file_path="c.py", message="blocker msg"),
    ]
    result = builder.build_review(findings)
    # Blocker should come before Critical, Critical before Info
    blocker_pos = result.index("[BLOCKER]")
    critical_pos = result.index("[CRITICAL]")
    info_pos = result.index("[INFO]")
    assert blocker_pos < critical_pos < info_pos


def test_comment_builder_footer():
    builder = CommentBuilder()
    findings = [Finding(engine="test", severity="info", file_path="x.py", message="test")]
    result = builder.build_review(findings)
    assert "PR-CodeGuard Agent" in result
    assert "1 issues found" in result
