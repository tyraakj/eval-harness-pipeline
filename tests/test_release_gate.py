from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from langgraph_eval.core.models import (
    ReleaseDecision,
    ReleasePolicy,
    RunSummary,
    SuiteSummary,
    SuiteType,
)
from langgraph_eval.evaluation.release_gate import ReleaseGate


@pytest.fixture
def sample_run_summary() -> RunSummary:
    """Create a sample RunSummary for testing."""
    return RunSummary(
        schema_version="1.0",
        run_id="test-run-123",
        evaluation_suite_id="test-suite",
        evaluation_suite_version="1.0.0",
        started_at=datetime.now(UTC),
        total=10,
        cases=10,
        repetitions=1,
        passed=9,
        failed=1,
        errors=0,
        timeouts=0,
        pass_rate=0.9,
        average_score=0.85,
        pass_at_k=0.9,
        pass_power_k=0.8,
        judge_cost_usd=0.0,
        suites={
            SuiteType.CAPABILITY: SuiteSummary(
                trials=6, passed=5, failed=1, errors=0, pass_rate=0.833, average_score=0.9
            ),
            SuiteType.REGRESSION: SuiteSummary(
                trials=3, passed=3, failed=0, errors=0, pass_rate=1.0, average_score=0.95
            ),
            SuiteType.SECURITY: SuiteSummary(
                trials=1, passed=1, failed=0, errors=0, pass_rate=1.0, average_score=1.0
            ),
        },
        export_errors=(),
        artifact_path="artifacts/test.jsonl",
    )


@pytest.fixture
def sample_candidate_artifact(tmp_path: Path) -> Path:
    """Create a sample candidate artifact file."""
    artifact_path = tmp_path / "candidate.jsonl"
    lines = [
        json.dumps({
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "trial_id": "trial-1",
            "case_id": "case-1",
            "repetition_index": 0,
            "suite": "capability",
            "started_at": datetime.now(UTC).isoformat(),
            "duration_ms": 1000,
            "status": "passed",
            "input_hash": "abc123",
            "grades": [],
            "tracked_metrics": [],
            "metrics": {},
            "score": 1.0,
            "provenance": {
                "harness_version": "0.1.0",
                "code_revision": "abc123",
                "dataset_hash": "hash123",
                "target_hash": "target123",
            },
        }),
        json.dumps({
            "schema_version": "1.0",
            "run_id": "test-run-123",
            "trial_id": "trial-2",
            "case_id": "case-2",
            "repetition_index": 0,
            "suite": "capability",
            "started_at": datetime.now(UTC).isoformat(),
            "duration_ms": 1000,
            "status": "failed",
            "input_hash": "def456",
            "grades": [],
            "tracked_metrics": [],
            "metrics": {},
            "score": 0.0,
            "provenance": {
                "harness_version": "0.1.0",
                "code_revision": "abc123",
                "dataset_hash": "hash123",
                "target_hash": "target123",
            },
        }),
    ]
    artifact_path.write_text("\n".join(lines))
    return artifact_path


@pytest.fixture
def sample_baseline_artifact(tmp_path: Path) -> Path:
    """Create a sample baseline artifact file."""
    artifact_path = tmp_path / "baseline.jsonl"
    lines = [
        json.dumps({
            "schema_version": "1.0",
            "run_id": "baseline-run-123",
            "trial_id": "trial-1",
            "case_id": "case-1",
            "repetition_index": 0,
            "suite": "capability",
            "started_at": datetime.now(UTC).isoformat(),
            "duration_ms": 1000,
            "status": "passed",
            "input_hash": "abc123",
            "grades": [],
            "tracked_metrics": [],
            "metrics": {},
            "score": 1.0,
            "provenance": {
                "harness_version": "0.1.0",
                "code_revision": "xyz789",
                "dataset_hash": "hash123",
                "target_hash": "target456",
            },
        }),
        json.dumps({
            "schema_version": "1.0",
            "run_id": "baseline-run-123",
            "trial_id": "trial-2",
            "case_id": "case-2",
            "repetition_index": 0,
            "suite": "capability",
            "started_at": datetime.now(UTC).isoformat(),
            "duration_ms": 1000,
            "status": "passed",  # Different from candidate
            "input_hash": "def456",
            "grades": [],
            "tracked_metrics": [],
            "metrics": {},
            "score": 1.0,
            "provenance": {
                "harness_version": "0.1.0",
                "code_revision": "xyz789",
                "dataset_hash": "hash123",
                "target_hash": "target456",
            },
        }),
    ]
    artifact_path.write_text("\n".join(lines))
    return artifact_path


class TestReleasePolicy:
    """Test ReleasePolicy validation and creation."""

    def test_default_policy(self) -> None:
        """Test default ReleasePolicy creation."""
        policy = ReleasePolicy()
        assert policy.require_deterministic is True
        assert policy.require_regression_check is False
        assert policy.require_judge is False
        assert policy.minimum_overall_pass_rate == 1.0
        assert policy.maximum_regressions == 0

    def test_regression_requires_deterministic(self) -> None:
        """Test that regression check requires deterministic evaluation."""
        with pytest.raises(ValueError, match="Regression check requires deterministic evaluation"):
            ReleasePolicy(
                require_deterministic=False,
                require_regression_check=True,
            )

    def test_judge_requires_deterministic(self) -> None:
        """Test that judge evaluation requires deterministic evaluation."""
        with pytest.raises(ValueError, match="Judge evaluation requires deterministic evaluation"):
            ReleasePolicy(
                require_deterministic=False,
                require_judge=True,
            )

    def test_pass_rate_bounds(self) -> None:
        """Test that pass rate thresholds are within valid bounds."""
        with pytest.raises(ValueError):
            ReleasePolicy(minimum_overall_pass_rate=1.5)
        
        with pytest.raises(ValueError):
            ReleasePolicy(minimum_overall_pass_rate=-0.1)

    def test_custom_policy(self) -> None:
        """Test custom ReleasePolicy with specific thresholds."""
        policy = ReleasePolicy(
            minimum_overall_pass_rate=0.95,
            minimum_capability_pass_rate=0.9,
            maximum_regressions=5,
            minimum_pass_rate_delta=-0.1,
        )
        assert policy.minimum_overall_pass_rate == 0.95
        assert policy.minimum_capability_pass_rate == 0.9
        assert policy.maximum_regressions == 5
        assert policy.minimum_pass_rate_delta == -0.1


class TestReleaseGate:
    """Test ReleaseGate evaluation logic."""

    @pytest.mark.asyncio
    async def test_deterministic_only_pass(self, sample_run_summary: RunSummary) -> None:
        """Test release gate with only deterministic evaluation (passing)."""
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_regression_check=False,
                require_judge=False,
                minimum_overall_pass_rate=0.8,
                minimum_capability_pass_rate=0.8,  # Lower than sample's 0.833
            )
        )
        
        decision = await gate.evaluate_release(sample_run_summary)
        
        assert decision.allowed is True
        assert decision.deterministics_passed is True
        assert "passed" in decision.reason.lower()
        assert decision.overall_pass_rate == 0.9

    @pytest.mark.asyncio
    async def test_deterministic_only_fail(self, sample_run_summary: RunSummary) -> None:
        """Test release gate with only deterministic evaluation (failing)."""
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_regression_check=False,
                require_judge=False,
                minimum_overall_pass_rate=0.95,  # Higher than actual 0.9
            )
        )
        
        decision = await gate.evaluate_release(sample_run_summary)
        
        assert decision.allowed is False
        assert decision.deterministics_passed is False
        assert "below threshold" in decision.deterministics_rationale.lower()

    @pytest.mark.asyncio
    async def test_suite_specific_thresholds(self, sample_run_summary: RunSummary) -> None:
        """Test suite-specific pass rate thresholds."""
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                minimum_capability_pass_rate=0.9,  # Higher than actual 0.833
            )
        )
        
        decision = await gate.evaluate_release(sample_run_summary)
        
        assert decision.allowed is False
        assert "capability" in decision.deterministics_rationale.lower()

    @pytest.mark.asyncio
    async def test_error_rate_check(self) -> None:
        """Test error rate threshold enforcement."""
        summary = RunSummary(
            schema_version="1.0",
            run_id="test-run",
            evaluation_suite_id="test-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=10,
            cases=10,
            repetitions=1,
            passed=8,
            failed=0,
            errors=2,  # 20% error rate
            timeouts=0,
            pass_rate=0.8,
            average_score=0.8,
            pass_at_k=0.8,
            pass_power_k=0.8,
            judge_cost_usd=0.0,
            suites={},
            export_errors=(),
            artifact_path="artifacts/test.jsonl",
        )
        
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                maximum_error_rate=0.1,  # Lower than actual 0.2
            )
        )
        
        decision = await gate.evaluate_release(summary)
        
        assert decision.allowed is False
        assert "error rate" in decision.deterministics_rationale.lower()

    @pytest.mark.asyncio
    async def test_regression_check_pass(
        self,
        sample_run_summary: RunSummary,
        sample_candidate_artifact: Path,
        sample_baseline_artifact: Path,
    ) -> None:
        """Test regression check with no regressions."""
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_regression_check=True,
                maximum_regressions=0,
            )
        )
        
        # Use the actual artifact path from the fixture
        summary_with_real_path = sample_run_summary.model_copy(
            update={"artifact_path": str(sample_candidate_artifact)}
        )
        
        decision = await gate.evaluate_release(
            summary_with_real_path,
            comparison_baseline=sample_baseline_artifact,
        )
        
        # Should have 1 regression (case-2 passed in baseline, failed in candidate)
        assert decision.regression_count == 1
        assert decision.regression_passed is False  # Due to regression

    @pytest.mark.asyncio
    async def test_regression_check_disabled(
        self,
        sample_run_summary: RunSummary,
        sample_baseline_artifact: Path,
        sample_candidate_artifact: Path,
    ) -> None:
        """Test that regression check is skipped when not required."""
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_regression_check=False,  # Disabled
            )
        )
        
        # Use the actual artifact path from the fixture
        summary_with_real_path = sample_run_summary.model_copy(
            update={"artifact_path": str(sample_candidate_artifact)}
        )
        
        decision = await gate.evaluate_release(
            summary_with_real_path,
            comparison_baseline=sample_baseline_artifact,  # Provided but not required
        )
        
        assert decision.regression_passed is True
        assert "not required" in decision.regression_rationale.lower()

    @pytest.mark.asyncio
    async def test_judge_evaluation_pass(self) -> None:
        """Test judge evaluation with passing score."""
        judge_summary = RunSummary(
            schema_version="1.0",
            run_id="judge-run",
            evaluation_suite_id="judge-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=5,
            cases=5,
            repetitions=1,
            passed=4,
            failed=1,
            errors=0,
            timeouts=0,
            pass_rate=0.8,
            average_score=0.85,  # Above threshold
            pass_at_k=0.8,
            pass_power_k=0.8,
            judge_cost_usd=5.0,
            suites={},
            export_errors=(),
            artifact_path="artifacts/judge.jsonl",
        )
        
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_judge=True,
                minimum_judge_score=0.8,
                maximum_judge_cost_usd=10.0,
            )
        )
        
        deterministic_summary = RunSummary(
            schema_version="1.0",
            run_id="det-run",
            evaluation_suite_id="det-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=10,
            cases=10,
            repetitions=1,
            passed=10,
            failed=0,
            errors=0,
            timeouts=0,
            pass_rate=1.0,
            average_score=1.0,
            pass_at_k=1.0,
            pass_power_k=1.0,
            judge_cost_usd=0.0,
            suites={},
            export_errors=(),
            artifact_path="artifacts/det.jsonl",
        )
        
        decision = await gate.evaluate_release(
            deterministic_summary,
            judge_summary=judge_summary,
        )
        
        assert decision.judge_passed is True
        assert decision.judge_score == 0.85

    @pytest.mark.asyncio
    async def test_judge_evaluation_fail_score(self) -> None:
        """Test judge evaluation with failing score."""
        judge_summary = RunSummary(
            schema_version="1.0",
            run_id="judge-run",
            evaluation_suite_id="judge-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=5,
            cases=5,
            repetitions=1,
            passed=4,
            failed=1,
            errors=0,
            timeouts=0,
            pass_rate=0.8,
            average_score=0.6,  # Below threshold
            pass_at_k=0.8,
            pass_power_k=0.8,
            judge_cost_usd=5.0,
            suites={},
            export_errors=(),
            artifact_path="artifacts/judge.jsonl",
        )
        
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_judge=True,
                minimum_judge_score=0.8,
            )
        )
        
        deterministic_summary = RunSummary(
            schema_version="1.0",
            run_id="det-run",
            evaluation_suite_id="det-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=10,
            cases=10,
            repetitions=1,
            passed=10,
            failed=0,
            errors=0,
            timeouts=0,
            pass_rate=1.0,
            average_score=1.0,
            pass_at_k=1.0,
            pass_power_k=1.0,
            judge_cost_usd=0.0,
            suites={},
            export_errors=(),
            artifact_path="artifacts/det.jsonl",
        )
        
        decision = await gate.evaluate_release(
            deterministic_summary,
            judge_summary=judge_summary,
        )
        
        assert decision.judge_passed is False
        assert "below threshold" in decision.judge_rationale.lower()

    @pytest.mark.asyncio
    async def test_judge_evaluation_fail_cost(self) -> None:
        """Test judge evaluation with excessive cost."""
        judge_summary = RunSummary(
            schema_version="1.0",
            run_id="judge-run",
            evaluation_suite_id="judge-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=5,
            cases=5,
            repetitions=1,
            passed=4,
            failed=1,
            errors=0,
            timeouts=0,
            pass_rate=0.8,
            average_score=0.9,
            pass_at_k=0.8,
            pass_power_k=0.8,
            judge_cost_usd=15.0,  # Exceeds maximum
            suites={},
            export_errors=(),
            artifact_path="artifacts/judge.jsonl",
        )
        
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_judge=True,
                minimum_judge_score=0.8,
                maximum_judge_cost_usd=10.0,
            )
        )
        
        deterministic_summary = RunSummary(
            schema_version="1.0",
            run_id="det-run",
            evaluation_suite_id="det-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=10,
            cases=10,
            repetitions=1,
            passed=10,
            failed=0,
            errors=0,
            timeouts=0,
            pass_rate=1.0,
            average_score=1.0,
            pass_at_k=1.0,
            pass_power_k=1.0,
            judge_cost_usd=0.0,
            suites={},
            export_errors=(),
            artifact_path="artifacts/det.jsonl",
        )
        
        decision = await gate.evaluate_release(
            deterministic_summary,
            judge_summary=judge_summary,
        )
        
        assert decision.judge_passed is False
        assert "cost" in decision.judge_rationale.lower()

    def test_create_strict_policy(self) -> None:
        """Test strict policy creation."""
        gate = ReleaseGate()
        policy = gate.create_strict_policy()
        
        assert policy.require_deterministic is True
        assert policy.require_regression_check is True
        assert policy.minimum_overall_pass_rate == 1.0
        assert policy.minimum_security_pass_rate == 1.0
        assert policy.maximum_error_rate == 0.0
        assert policy.maximum_regressions == 0

    def test_create_development_policy(self) -> None:
        """Test development policy creation."""
        gate = ReleaseGate()
        policy = gate.create_development_policy()
        
        assert policy.require_deterministic is True
        assert policy.require_regression_check is False
        assert policy.minimum_overall_pass_rate == 0.8
        assert policy.minimum_security_pass_rate == 1.0  # Security still strict
        assert policy.maximum_error_rate == 0.1
        assert policy.maximum_regressions == 5

    def test_create_staging_policy(self) -> None:
        """Test staging policy creation."""
        gate = ReleaseGate()
        policy = gate.create_staging_policy()
        
        assert policy.require_deterministic is True
        assert policy.require_regression_check is True
        assert policy.minimum_overall_pass_rate == 0.95
        assert policy.minimum_security_pass_rate == 1.0
        assert policy.maximum_error_rate == 0.05
        assert policy.maximum_regressions == 2

    @pytest.mark.asyncio
    async def test_missing_suite_handling(self) -> None:
        """Test handling when a suite is missing from results."""
        summary = RunSummary(
            schema_version="1.0",
            run_id="test-run",
            evaluation_suite_id="test-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=10,
            cases=10,
            repetitions=1,
            passed=10,
            failed=0,
            errors=0,
            timeouts=0,
            pass_rate=1.0,
            average_score=1.0,
            pass_at_k=1.0,
            pass_power_k=1.0,
            judge_cost_usd=0.0,
            suites={
                SuiteType.CAPABILITY: SuiteSummary(
                    trials=10, passed=10, failed=0, errors=0, pass_rate=1.0, average_score=1.0
                ),
                # Missing REGRESSION and SECURITY suites
            },
            export_errors=(),
            artifact_path="artifacts/test.jsonl",
        )
        
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                minimum_regression_pass_rate=0.9,  # High threshold for missing suite
                minimum_security_pass_rate=0.9,  # High threshold for missing suite
            )
        )
        
        decision = await gate.evaluate_release(summary)
        
        # Should pass because missing suites are not checked
        assert decision.allowed is True

    @pytest.mark.asyncio
    async def test_combined_evaluation_all_pass(self) -> None:
        """Test combined evaluation with all checks passing."""
        deterministic_summary = RunSummary(
            schema_version="1.0",
            run_id="det-run",
            evaluation_suite_id="det-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=10,
            cases=10,
            repetitions=1,
            passed=10,
            failed=0,
            errors=0,
            timeouts=0,
            pass_rate=1.0,
            average_score=1.0,
            pass_at_k=1.0,
            pass_power_k=1.0,
            judge_cost_usd=0.0,
            suites={
                SuiteType.CAPABILITY: SuiteSummary(
                    trials=6, passed=6, failed=0, errors=0, pass_rate=1.0, average_score=1.0
                ),
                SuiteType.SECURITY: SuiteSummary(
                    trials=4, passed=4, failed=0, errors=0, pass_rate=1.0, average_score=1.0
                ),
            },
            export_errors=(),
            artifact_path="artifacts/det.jsonl",
        )
        
        judge_summary = RunSummary(
            schema_version="1.0",
            run_id="judge-run",
            evaluation_suite_id="judge-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=5,
            cases=5,
            repetitions=1,
            passed=5,
            failed=0,
            errors=0,
            timeouts=0,
            pass_rate=1.0,
            average_score=0.95,
            pass_at_k=1.0,
            pass_power_k=1.0,
            judge_cost_usd=5.0,
            suites={},
            export_errors=(),
            artifact_path="artifacts/judge.jsonl",
        )
        
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_regression_check=False,
                require_judge=True,
                minimum_judge_score=0.9,
                maximum_judge_cost_usd=10.0,
            )
        )
        
        decision = await gate.evaluate_release(
            deterministic_summary,
            judge_summary=judge_summary,
        )
        
        assert decision.allowed is True
        assert decision.deterministics_passed is True
        assert decision.judge_passed is True

    @pytest.mark.asyncio
    async def test_combined_evaluation_one_fail(self) -> None:
        """Test combined evaluation with one check failing."""
        deterministic_summary = RunSummary(
            schema_version="1.0",
            run_id="det-run",
            evaluation_suite_id="det-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=10,
            cases=10,
            repetitions=1,
            passed=9,
            failed=1,
            errors=0,
            timeouts=0,
            pass_rate=0.9,
            average_score=0.9,
            pass_at_k=0.9,
            pass_power_k=0.9,
            judge_cost_usd=0.0,
            suites={
                SuiteType.CAPABILITY: SuiteSummary(
                    trials=6, passed=5, failed=1, errors=0, pass_rate=0.833, average_score=0.9
                ),
            },
            export_errors=(),
            artifact_path="artifacts/det.jsonl",
        )
        
        judge_summary = RunSummary(
            schema_version="1.0",
            run_id="judge-run",
            evaluation_suite_id="judge-suite",
            evaluation_suite_version="1.0.0",
            started_at=datetime.now(UTC),
            total=5,
            cases=5,
            repetitions=1,
            passed=5,
            failed=0,
            errors=0,
            timeouts=0,
            pass_rate=1.0,
            average_score=0.95,
            pass_at_k=1.0,
            pass_power_k=1.0,
            judge_cost_usd=5.0,
            suites={},
            export_errors=(),
            artifact_path="artifacts/judge.jsonl",
        )
        
        gate = ReleaseGate(
            policy=ReleasePolicy(
                require_deterministic=True,
                require_regression_check=False,
                require_judge=True,
                minimum_overall_pass_rate=0.95,  # Higher than actual 0.9
                minimum_judge_score=0.9,
            )
        )
        
        decision = await gate.evaluate_release(
            deterministic_summary,
            judge_summary=judge_summary,
        )
        
        assert decision.allowed is False
        assert decision.deterministics_passed is False
        assert decision.judge_passed is True
        assert "deterministic" in decision.reason.lower()


class TestReleaseDecision:
    """Test ReleaseDecision model."""

    def test_release_decision_creation(self) -> None:
        """Test ReleaseDecision model creation."""
        decision = ReleaseDecision(
            allowed=True,
            reason="All checks passed",
            deterministics_passed=True,
            deterministics_rationale="Deterministic checks passed",
            regression_passed=True,
            regression_rationale="Regression check not required",
            judge_passed=True,
            judge_rationale="Judge evaluation not required",
            overall_pass_rate=0.95,
            capability_pass_rate=0.93,
            regression_pass_rate=1.0,
            security_pass_rate=1.0,
            error_rate=0.0,
            regression_count=0,
            pass_rate_delta=0.02,
            judge_score=0.0,
            judge_cost_usd=0.0,
        )
        
        assert decision.allowed is True
        assert decision.overall_pass_rate == 0.95
        assert decision.regression_count == 0

    def test_release_decision_immutable(self) -> None:
        """Test that ReleaseDecision is immutable."""
        decision = ReleaseDecision(
            allowed=True,
            reason="Test",
        )
        
        with pytest.raises(ValidationError):  # Pydantic frozen model raises ValidationError
            decision.allowed = False