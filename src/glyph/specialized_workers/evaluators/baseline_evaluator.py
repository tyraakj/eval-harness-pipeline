"""Baseline and candidate service for comparative evaluation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from glyph.specialized_workers.artifact import EvaluationArtifact

logger = logging.getLogger(__name__)


class ComparisonResult(StrEnum):
    """Result of comparing candidate to baseline."""
    PASSED = "passed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    NOT_COMPARABLE = "not_comparable"


@dataclass
class BaselineRun:
    """Represents a baseline evaluation run."""
    run_id: str
    target_version: str
    dataset_version: str
    
    # Execution details
    executed_at: datetime
    mode: str  # "live" (baseline is always live)
    
    # Artifacts
    artifact_ids: list[str] = field(default_factory=list)
    
    # Baseline quality metrics
    overall_score: float = 0.0
    deterministic_grades: dict[str, int] = field(default_factory=dict)
    ai_grades: dict[str, int] = field(default_factory=dict)
    
    # Token usage
    token_usage: dict[str, int] = field(default_factory=dict)
    
    # Quality policy
    quality_policy_passed: bool = True
    quality_policy_reason: str = ""


@dataclass
class CandidateRun:
    """Represents a candidate evaluation run."""
    run_id: str
    target_version: str
    dataset_version: str
    
    # Execution details
    executed_at: datetime
    mode: str  # "live" or "replay"
    
    # Artifacts
    artifact_ids: list[str] = field(default_factory=list)
    
    # Token usage
    target_tokens_used: int = 0
    evaluator_tokens_used: int = 0
    
    # Cache statistics
    cache_hits: int = 0
    cache_misses: int = 0


@dataclass
class TrialComparison:
    """Comparison of a single trial between baseline and candidate."""
    case_id: str
    trial_id: str
    
    baseline_artifact_id: str
    candidate_artifact_id: str
    
    # Comparison results
    behavior_changed: bool = False
    output_changed: bool = False
    performance_delta: dict[str, float] = field(default_factory=dict)
    
    # Grade comparison
    baseline_grade: dict[str, Any] = field(default_factory=dict)
    candidate_grade: dict[str, Any] = field(default_factory=dict)
    grade_regression: bool = False
    
    # Final verdict
    passed: bool = True
    reason: str = ""


@dataclass
class BaselineComparison:
    """Complete comparison between baseline and candidate runs."""
    baseline_run: BaselineRun
    candidate_run: CandidateRun
    
    # Overall decision
    decision: ComparisonResult
    reason_codes: list[str] = field(default_factory=list)
    
    # Trial-level comparisons
    trial_comparisons: list[TrialComparison] = field(default_factory=list)
    
    # Summary statistics
    total_trials: int = 0
    passed_trials: int = 0
    failed_trials: int = 0
    behavior_changed_trials: int = 0
    
    # Token comparison
    baseline_tokens: int = 0
    candidate_tokens: int = 0
    token_savings: int = 0
    
    # Performance comparison
    baseline_avg_latency_ms: float = 0.0
    candidate_avg_latency_ms: float = 0.0
    latency_delta_ms: float = 0.0
    
    # Blocking trials
    blocking_trials: list[str] = field(default_factory=list)


class BaselineService:
    """
    Service for managing baseline evaluations.
    
    The baseline is executed once in live mode and then frozen.
    Candidates are compared against this baseline.
    """
    
    def __init__(self, storage_manager):
        self.storage = storage_manager
        self._baselines: dict[str, BaselineRun] = {}  # dataset_version -> BaselineRun
    
    def create_baseline(
        self,
        run_id: str,
        target_version: str,
        dataset_version: str,
        artifact_ids: list[str],
        overall_score: float = 0.0,
    ) -> BaselineRun:
        """
        Create a baseline run from live execution.
        
        The baseline is executed once in live mode and then frozen.
        It serves as the comparison reference for all future candidates.
        """
        baseline = BaselineRun(
            run_id=run_id,
            target_version=target_version,
            dataset_version=dataset_version,
            executed_at=datetime.now(UTC),
            mode="live",
            artifact_ids=artifact_ids,
            overall_score=overall_score,
        )
        
        self._baselines[dataset_version] = baseline
        
        # Store metadata
        from glyph.specialized_workers.infra.storage_layers import RunMetadata
        metadata = RunMetadata(
            run_id=run_id,
            project_id="baseline",
            user_id="system",
            target_version=target_version,
            dataset_version=dataset_version,
            mode="live",
            status="completed",
            created_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            artifact_ids=artifact_ids,
        )
        self.storage.store_run_metadata(metadata)
        
        logger.info(
            f"Created baseline {run_id} for dataset {dataset_version} "
            f"with {len(artifact_ids)} artifacts"
        )
        
        return baseline
    
    def get_baseline(self, dataset_version: str) -> BaselineRun | None:
        """Get the baseline for a dataset version."""
        return self._baselines.get(dataset_version)
    
    def get_baseline_artifact(
        self,
        dataset_version: str,
        case_id: str,
    ) -> EvaluationArtifact | None:
        """Get a specific baseline artifact."""
        baseline = self.get_baseline(dataset_version)
        if not baseline:
            return None
        
        # Find artifact for this case
        for artifact_id in baseline.artifact_ids:
            artifact = self.storage.get_artifact(artifact_id)
            if artifact and artifact.case_id == case_id:
                return artifact
        
        return None
    
    def is_baseline_compatible(
        self,
        dataset_version: str,
        candidate_dataset_version: str,
    ) -> bool:
        """
        Check if a candidate is compatible with the baseline.
        
        Baseline and candidate must use the same dataset version.
        """
        return dataset_version == candidate_dataset_version


class CandidateService:
    """
    Service for managing candidate evaluations.
    
    Candidates run against the exact same dataset, case IDs, fixtures,
    graders, sandbox policy, and evaluation configuration as the baseline.
    """
    
    def __init__(self, storage_manager):
        self.storage = storage_manager
        self._candidates: dict[str, CandidateRun] = {}  # run_id -> CandidateRun
    
    def create_candidate(
        self,
        run_id: str,
        target_version: str,
        dataset_version: str,
        mode: str,
        artifact_ids: list[str],
        target_tokens_used: int = 0,
        evaluator_tokens_used: int = 0,
        cache_hits: int = 0,
        cache_misses: int = 0,
    ) -> CandidateRun:
        """Create a candidate run."""
        candidate = CandidateRun(
            run_id=run_id,
            target_version=target_version,
            dataset_version=dataset_version,
            executed_at=datetime.now(UTC),
            mode=mode,
            artifact_ids=artifact_ids,
            target_tokens_used=target_tokens_used,
            evaluator_tokens_used=evaluator_tokens_used,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
        )
        
        self._candidates[run_id] = candidate
        
        # Store metadata
        from glyph.specialized_workers.infra.storage_layers import RunMetadata
        metadata = RunMetadata(
            run_id=run_id,
            project_id="candidate",
            user_id="system",
            target_version=target_version,
            dataset_version=dataset_version,
            mode=mode,
            status="completed",
            created_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            artifact_ids=artifact_ids,
            target_tokens_used=target_tokens_used,
            evaluator_tokens_used=evaluator_tokens_used,
            cache_hits=cache_hits,
            cache_misses=cache_misses,
        )
        self.storage.store_run_metadata(metadata)
        
        logger.info(
            f"Created candidate {run_id} for dataset {dataset_version} "
            f"with {len(artifact_ids)} artifacts (mode={mode})"
        )
        
        return candidate
    
    def get_candidate(self, run_id: str) -> CandidateRun | None:
        """Get a candidate run by ID."""
        return self._candidates.get(run_id)
    
    def get_candidate_artifact(
        self,
        run_id: str,
        case_id: str,
    ) -> EvaluationArtifact | None:
        """Get a specific candidate artifact."""
        candidate = self.get_candidate(run_id)
        if not candidate:
            return None
        
        # Find artifact for this case
        for artifact_id in candidate.artifact_ids:
            artifact = self.storage.get_artifact(artifact_id)
            if artifact and artifact.case_id == case_id:
                return artifact
        
        return None


class BaselineComparator:
    """
    Compares candidate runs against baseline runs.
    
    The comparison is done by stable case ID, ensuring that
    the same test case is compared between baseline and candidate.
    """
    
    def __init__(
        self,
        baseline_service: BaselineService,
        candidate_service: CandidateService,
    ):
        self.baseline_service = baseline_service
        self.candidate_service = candidate_service
    
    def compare(
        self,
        baseline_run_id: str,
        candidate_run_id: str,
    ) -> BaselineComparison:
        """
        Compare a candidate run against a baseline run.
        
        Returns:
            BaselineComparison with detailed comparison results
        """
        # Get baseline and candidate
        baseline = self._get_baseline_by_run_id(baseline_run_id)
        candidate = self.candidate_service.get_candidate(candidate_run_id)
        
        if not baseline:
            return BaselineComparison(
                baseline_run=BaselineRun(
                    run_id=baseline_run_id,
                    target_version="unknown",
                    dataset_version="unknown",
                    executed_at=datetime.now(UTC),
                    mode="live",
                ),
                candidate_run=candidate or CandidateRun(
                    run_id=candidate_run_id,
                    target_version="unknown",
                    dataset_version="unknown",
                    executed_at=datetime.now(UTC),
                    mode="unknown",
                ),
                decision=ComparisonResult.NOT_COMPARABLE,
                reason_codes=["baseline_not_found"],
            )
        
        if not candidate:
            return BaselineComparison(
                baseline_run=baseline,
                candidate_run=CandidateRun(
                    run_id=candidate_run_id,
                    target_version="unknown",
                    dataset_version="unknown",
                    executed_at=datetime.now(UTC),
                    mode="unknown",
                ),
                decision=ComparisonResult.NOT_COMPARABLE,
                reason_codes=["candidate_not_found"],
            )
        
        # Check dataset compatibility
        if not self.baseline_service.is_baseline_compatible(
            baseline.dataset_version,
            candidate.dataset_version,
        ):
            return BaselineComparison(
                baseline_run=baseline,
                candidate_run=candidate,
                decision=ComparisonResult.NOT_COMPARABLE,
                reason_codes=["dataset_version_mismatch"],
            )
        
        # Compare trials
        trial_comparisons = self._compare_trials(baseline, candidate)
        
        # Calculate summary statistics
        total_trials = len(trial_comparisons)
        passed_trials = sum(1 for tc in trial_comparisons if tc.passed)
        failed_trials = total_trials - passed_trials
        behavior_changed_trials = sum(
            1 for tc in trial_comparisons if tc.behavior_changed
        )
        
        # Identify blocking trials
        blocking_trials = [
            tc.trial_id for tc in trial_comparisons
            if not tc.passed and tc.grade_regression
        ]
        
        # Make final decision
        decision, reason_codes = self._make_decision(
            trial_comparisons,
            blocking_trials,
        )
        
        # Calculate token comparison
        baseline_tokens = baseline.token_usage.get("total", 0)
        candidate_tokens = (
            candidate.target_tokens_used + candidate.evaluator_tokens_used
        )
        token_savings = baseline_tokens - candidate_tokens
        
        # Calculate performance comparison
        baseline_avg_latency_ms = self._calculate_avg_latency(baseline)
        candidate_avg_latency_ms = self._calculate_avg_latency(candidate)
        latency_delta_ms = candidate_avg_latency_ms - baseline_avg_latency_ms
        
        return BaselineComparison(
            baseline_run=baseline,
            candidate_run=candidate,
            decision=decision,
            reason_codes=reason_codes,
            trial_comparisons=trial_comparisons,
            total_trials=total_trials,
            passed_trials=passed_trials,
            failed_trials=failed_trials,
            behavior_changed_trials=behavior_changed_trials,
            baseline_tokens=baseline_tokens,
            candidate_tokens=candidate_tokens,
            token_savings=token_savings,
            baseline_avg_latency_ms=baseline_avg_latency_ms,
            candidate_avg_latency_ms=candidate_avg_latency_ms,
            latency_delta_ms=latency_delta_ms,
            blocking_trials=blocking_trials,
        )
    
    def _get_baseline_by_run_id(self, run_id: str) -> BaselineRun | None:
        """Find baseline by run ID."""
        for baseline in self.baseline_service._baselines.values():
            if baseline.run_id == run_id:
                return baseline
        return None
    
    def _compare_trials(
        self,
        baseline: BaselineRun,
        candidate: CandidateRun,
    ) -> list[TrialComparison]:
        """Compare trials between baseline and candidate."""
        comparisons = []
        
        # Compare by stable case ID
        for baseline_artifact_id in baseline.artifact_ids:
            baseline_artifact = self.baseline_service.storage.get_artifact(
                baseline_artifact_id
            )
            if not baseline_artifact:
                continue
            
            # Find matching candidate artifact
            candidate_artifact = None
            for candidate_artifact_id in candidate.artifact_ids:
                artifact = self.candidate_service.storage.get_artifact(
                    candidate_artifact_id
                )
                if artifact and artifact.case_id == baseline_artifact.case_id:
                    candidate_artifact = artifact
                    break
            
            if not candidate_artifact:
                continue
            
            # Compare the artifacts
            comparison = self._compare_artifacts(
                baseline_artifact,
                candidate_artifact,
            )
            comparisons.append(comparison)
        
        return comparisons
    
    def _compare_artifacts(
        self,
        baseline_artifact: EvaluationArtifact,
        candidate_artifact: EvaluationArtifact,
    ) -> TrialComparison:
        """Compare two artifacts for the same case."""
        import json
        
        # Check if output changed
        baseline_output = json.dumps(
            baseline_artifact.final_output,
            sort_keys=True,
            default=str,
        )
        candidate_output = json.dumps(
            candidate_artifact.final_output,
            sort_keys=True,
            default=str,
        )
        output_changed = baseline_output != candidate_output
        
        # Check if behavior changed (events)
        baseline_events = json.dumps(
            baseline_artifact.events,
            sort_keys=True,
            default=str,
        )
        candidate_events = json.dumps(
            candidate_artifact.events,
            sort_keys=True,
            default=str,
        )
        behavior_changed = baseline_events != candidate_events
        
        # Performance delta
        performance_delta = {}
        if baseline_artifact.usage and candidate_artifact.usage:
            performance_delta["input_tokens_delta"] = (
                candidate_artifact.usage.input_tokens -
                baseline_artifact.usage.input_tokens
            )
            performance_delta["output_tokens_delta"] = (
                candidate_artifact.usage.output_tokens -
                baseline_artifact.usage.output_tokens
            )
            performance_delta["cost_delta"] = (
                candidate_artifact.usage.estimated_cost -
                baseline_artifact.usage.estimated_cost
            )
        
        # Determine if passed (no regression)
        # This is a simplified check - in practice, would use grader results
        passed = not (behavior_changed and output_changed)
        grade_regression = behavior_changed and output_changed
        
        return TrialComparison(
            case_id=baseline_artifact.case_id,
            trial_id=baseline_artifact.trial_id,
            baseline_artifact_id=baseline_artifact.artifact_id,
            candidate_artifact_id=candidate_artifact.artifact_id,
            behavior_changed=behavior_changed,
            output_changed=output_changed,
            performance_delta=performance_delta,
            passed=passed,
            grade_regression=grade_regression,
            reason="behavior_change" if behavior_changed else "no_change",
        )
    
    def _make_decision(
        self,
        trial_comparisons: list[TrialComparison],
        blocking_trials: list[str],
    ) -> tuple[ComparisonResult, list[str]]:
        """Make the final comparison decision."""
        if blocking_trials:
            return (
                ComparisonResult.BLOCKED,
                [f"blocking_trials: {len(blocking_trials)}"],
            )
        
        behavior_changed = any(tc.behavior_changed for tc in trial_comparisons)
        if behavior_changed:
            return (
                ComparisonResult.INCONCLUSIVE,
                ["behavior_changed_trials"],
            )
        
        return ComparisonResult.PASSED, []
    
    def _calculate_avg_latency(
        self,
        run: BaselineRun | CandidateRun,
    ) -> float:
        """Calculate average latency across all artifacts."""
        total_latency = 0.0
        count = 0
        
        for artifact_id in run.artifact_ids:
            artifact = self.baseline_service.storage.get_artifact(artifact_id)
            if artifact:
                # Extract latency from events or usage
                # This is simplified - in practice would track properly
                total_latency += 100.0  # Placeholder
                count += 1
        
        return total_latency / count if count > 0 else 0.0