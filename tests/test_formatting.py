from __future__ import annotations

from datetime import UTC, datetime

import pytest

from glyph.core.domain_models import (
    Grade,
    ReleaseDecision,
    RunSummary,
    SuiteSummary,
    TrialRecord,
    TrialStatus,
)
from glyph.grading.comparison import Comparison
from glyph.utils.formatting import (
    OutputFormat,
    format_comparison,
    format_release_decision,
    format_run_summary,
    format_trial_detail,
)


@pytest.fixture
def sample_run_summary() -> RunSummary:
    """Create a sample RunSummary for testing."""
    from glyph.core.domain_models import SuiteType
    return RunSummary(
        run_id="test-run-123",
        evaluation_suite_id="test-suite",
        evaluation_suite_version="1.0.0",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        total=10,
        cases=10,
        repetitions=1,
        passed=8,
        failed=1,
        errors=1,
        timeouts=0,
        pass_rate=0.8,
        average_score=0.85,
        artifact_path="artifacts/results.jsonl",
        suites={
            SuiteType.CAPABILITY: SuiteSummary(trials=6, passed=5, failed=1, errors=0, pass_rate=0.833, average_score=0.9),
            SuiteType.REGRESSION: SuiteSummary(trials=4, passed=3, failed=1, errors=0, pass_rate=0.75, average_score=0.8),
        },
    )


@pytest.fixture
def sample_comparison() -> Comparison:
    """Create a sample Comparison for testing."""
    from glyph.grading.comparison import Comparison
    return Comparison(
        common_cases=10,
        improved=("case1", "case2"),
        regressed=("case3",),
        unchanged=("case4", "case5", "case6", "case7"),
        candidate_pass_rate=0.8,
        baseline_pass_rate=0.7,
    )


@pytest.fixture
def sample_release_decision() -> ReleaseDecision:
    """Create a sample ReleaseDecision for testing."""
    return ReleaseDecision(
        allowed=True,
        reason="All policy checks passed",
        deterministics_passed=True,
        deterministics_rationale="Pass rate meets threshold",
        regression_passed=True,
        regression_rationale="No regressions detected",
        judge_passed=True,
        judge_rationale="Judge score acceptable",
        overall_pass_rate=0.95,
        capability_pass_rate=0.96,
        regression_pass_rate=1.0,
        security_pass_rate=1.0,
        error_rate=0.0,
        regression_count=0,
        pass_rate_delta=0.05,
        judge_score=0.85,
        judge_cost_usd=5.50,
    )


@pytest.fixture
def sample_trial_record() -> TrialRecord:
    """Create a sample TrialRecord for testing."""
    from glyph.core.domain_models import Provenance
    return TrialRecord(
        schema_version="1.0",
        run_id="test-run-123",
        trial_id="trial-123",
        case_id="case-1",
        repetition_index=0,
        suite="capability",
        started_at=datetime.now(UTC),
        duration_ms=500,
        status=TrialStatus.PASSED,
        input_hash="input123",
        score=1.0,
        grades=[
            Grade(grader="exact_match", version="1.0", passed=True, score=1.0, reason="Match", evidence={}),
            Grade(grader="contains_all", version="1.0", passed=True, score=1.0, reason="Contains", evidence={}),
        ],
        provenance=Provenance(
            harness_version="1.0.0",
            code_revision="abc123",
            dataset_hash="hash123",
            target_hash="target123",
        ),
    )


def test_format_run_summary_rich(sample_run_summary: RunSummary, capsys):
    """Test that rich formatting for run summary doesn't raise exceptions."""
    format_run_summary(sample_run_summary, output_format=OutputFormat.RICH)
    captured = capsys.readouterr()
    # Should have output
    assert len(captured.out) > 0


def test_format_run_summary_json(sample_run_summary: RunSummary, capsys):
    """Test that JSON formatting produces valid JSON."""
    format_run_summary(sample_run_summary, output_format=OutputFormat.JSON)
    captured = capsys.readouterr()
    # Should be valid JSON
    import json
    data = json.loads(captured.out)
    assert data["run_id"] == "test-run-123"
    assert data["pass_rate"] == 0.8


def test_format_run_summary_pr_comment(sample_run_summary: RunSummary, capsys):
    """Test that PR comment formatting produces Markdown."""
    format_run_summary(sample_run_summary, output_format=OutputFormat.PR_COMMENT)
    captured = capsys.readouterr()
    # Should contain Markdown headers
    assert "## Evaluation Results" in captured.out
    assert "| Metric | Value |" in captured.out


def test_format_comparison_rich(sample_comparison: Comparison, capsys):
    """Test that rich formatting for comparison doesn't raise exceptions."""
    format_comparison(sample_comparison, output_format=OutputFormat.RICH)
    captured = capsys.readouterr()
    # Should have output
    assert len(captured.out) > 0


def test_format_comparison_json(sample_comparison: Comparison, capsys):
    """Test that JSON formatting for comparison produces valid JSON."""
    format_comparison(sample_comparison, output_format=OutputFormat.JSON)
    captured = capsys.readouterr()
    # Should be valid JSON
    import json
    data = json.loads(captured.out)
    assert data["common_cases"] == 10
    assert data["candidate_pass_rate"] == 0.8
    # JSON converts tuples to lists
    assert data["improved"] == ["case1", "case2"]


def test_format_comparison_pr_comment(sample_comparison: Comparison, capsys):
    """Test that PR comment formatting for comparison produces Markdown."""
    format_comparison(sample_comparison, output_format=OutputFormat.PR_COMMENT)
    captured = capsys.readouterr()
    # Should contain Markdown headers
    assert "## Comparison Results" in captured.out
    assert "| Metric | Value |" in captured.out


def test_format_release_decision_rich(sample_release_decision: ReleaseDecision, capsys):
    """Test that rich formatting for release decision doesn't raise exceptions."""
    format_release_decision(sample_release_decision, output_format=OutputFormat.RICH)
    captured = capsys.readouterr()
    # Should have output
    assert len(captured.out) > 0


def test_format_release_decision_json(sample_release_decision: ReleaseDecision, capsys):
    """Test that JSON formatting for release decision produces valid JSON."""
    format_release_decision(sample_release_decision, output_format=OutputFormat.JSON)
    captured = capsys.readouterr()
    # Should be valid JSON
    import json
    data = json.loads(captured.out)
    assert data["allowed"] is True
    assert data["overall_pass_rate"] == 0.95


def test_format_release_decision_pr_comment(sample_release_decision: ReleaseDecision, capsys):
    """Test that PR comment formatting for release decision produces Markdown."""
    format_release_decision(sample_release_decision, output_format=OutputFormat.PR_COMMENT)
    captured = capsys.readouterr()
    # Should contain Markdown headers
    assert "## RELEASE ALLOWED" in captured.out
    assert "| Check | Requirement | Status |" in captured.out


def test_format_trial_detail_rich(sample_trial_record: TrialRecord, capsys):
    """Test that rich formatting for trial detail doesn't raise exceptions."""
    format_trial_detail(sample_trial_record, output_format=OutputFormat.RICH)
    captured = capsys.readouterr()
    # Should have output
    assert len(captured.out) > 0


def test_format_trial_detail_json(sample_trial_record: TrialRecord, capsys):
    """Test that JSON formatting for trial detail produces valid JSON."""
    format_trial_detail(sample_trial_record, output_format=OutputFormat.JSON)
    captured = capsys.readouterr()
    # Should be valid JSON
    import json
    data = json.loads(captured.out)
    assert data["trial_id"] == "trial-123"
    assert data["case_id"] == "case-1"


def test_format_trial_detail_pr_comment(sample_trial_record: TrialRecord, capsys):
    """Test that PR comment formatting for trial detail produces Markdown."""
    format_trial_detail(sample_trial_record, output_format=OutputFormat.PR_COMMENT)
    captured = capsys.readouterr()
    # Should contain Markdown headers
    assert "## Trial Detail:" in captured.out
    assert "| Field | Value |" in captured.out


def test_format_run_summary_blocked_release(capsys):
    """Test formatting for a blocked release decision."""
    decision = ReleaseDecision(
        allowed=False,
        reason="Pass rate below threshold",
        deterministics_passed=False,
        deterministics_rationale="Pass rate 0.5 < 0.9 threshold",
        regression_passed=True,
        regression_rationale="",
        judge_passed=True,
        judge_rationale="",
        overall_pass_rate=0.5,
        capability_pass_rate=0.5,
        regression_pass_rate=1.0,
        security_pass_rate=1.0,
        error_rate=0.0,
        regression_count=0,
        pass_rate_delta=0.0,
        judge_score=0.0,
        judge_cost_usd=0.0,
    )
    format_release_decision(decision, output_format=OutputFormat.RICH)
    captured = capsys.readouterr()
    # Should show blocked banner
    assert len(captured.out) > 0


def test_format_comparison_negative_delta(capsys):
    """Test formatting for comparison with negative delta (regression)."""
    from glyph.grading.comparison import Comparison
    comparison = Comparison(
        common_cases=10,
        improved=(),
        regressed=("case1", "case2", "case3"),
        unchanged=("case4", "case5", "case6", "case7"),
        candidate_pass_rate=0.6,
        baseline_pass_rate=0.8,
    )
    format_comparison(comparison, output_format=OutputFormat.RICH)
    captured = capsys.readouterr()
    # Should have output
    assert len(captured.out) > 0


def test_create_progress_callback():
    """Test that progress callback creation works."""
    from glyph.utils.formatting import create_progress_callback
    
    progress, callback = create_progress_callback(total_trials=10)
    assert progress is not None
    assert callback is not None
    # Should not raise when called
    # Note: We can't easily test the actual progress bar update without
    # running the progress context manager, but we can verify the callback exists
