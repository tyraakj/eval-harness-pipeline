"""Aggregator and policy engine for final release decisions."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from glyph.specialized_workers.base import (
    Severity,
    WorkerResult,
    WorkerType,
)


class ReleaseDecision(StrEnum):
    """Final release decision matching the architecture."""
    PASSED = "passed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    NOT_COMPARABLE = "not_comparable"


@dataclass
class AggregationPolicy:
    """Policy for aggregating worker results into release decisions."""
    # Score thresholds
    minimum_overall_score: float = 0.8
    minimum_tool_score: float = 0.9
    minimum_retrieval_score: float = 0.7
    minimum_graph_score: float = 0.8
    minimum_output_score: float = 0.8
    minimum_performance_score: float = 0.6
    
    # Critical failure handling
    block_on_critical_security: bool = True
    block_on_critical_tool: bool = True
    block_on_critical_graph: bool = True
    
    # Worker weights for overall score
    tool_weight: float = 0.2
    retrieval_weight: float = 0.15
    graph_weight: float = 0.15
    output_weight: float = 0.25
    security_weight: float = 0.15
    performance_weight: float = 0.1
    
    # Failure tolerance
    max_non_critical_failures: int = 2
    allow_conditional_approval: bool = True
    
    def validate_weights(self) -> None:
        """Validate that weights sum to 1.0."""
        total = (
            self.tool_weight +
            self.retrieval_weight +
            self.graph_weight +
            self.output_weight +
            self.security_weight +
            self.performance_weight
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Worker weights must sum to 1.0, got {total}")


@dataclass
class AggregatedResult:
    """Aggregated result from all workers."""
    aggregation_id: str
    trial_id: str
    
    # Individual worker results
    worker_results: dict[WorkerType, WorkerResult]
    
    # Normalized scores
    normalized_scores: dict[WorkerType, float]
    
    # Overall score
    overall_score: float
    
    # Per-domain summary
    domain_summary: dict[str, dict[str, Any]]
    
    # Critical failures
    critical_failures: list[dict[str, Any]]
    
    # Non-critical failures
    non_critical_failures: list[dict[str, Any]]
    
    # Final release decision
    release_decision: ReleaseDecision
    release_rationale: str
    
    # Policy applied
    policy_version: str
    
    # Architecture-compliant fields
    baseline_run: str | None = None
    candidate_run: str | None = None
    dataset_version: str | None = None
    deterministic_grades: dict[str, int] = field(default_factory=dict)
    ai_grades: dict[str, int] = field(default_factory=dict)
    token_usage: dict[str, Any] = field(default_factory=dict)
    blocking_trials: list[str] = field(default_factory=list)


class ResultAggregator:
    """Aggregates worker results and applies policy for release decisions."""
    
    def __init__(self, policy: AggregationPolicy | None = None, policy_version: str = "1.0.0"):
        self.policy = policy or AggregationPolicy()
        self.policy_version = policy_version
        self.policy.validate_weights()
    
    def aggregate(
        self,
        worker_results: dict[WorkerType, WorkerResult],
        trial_id: str,
    ) -> AggregatedResult:
        """Aggregate worker results into a final release decision."""
        aggregation_id = str(uuid.uuid4())
        
        # Normalize scores
        normalized_scores = self._normalize_scores(worker_results)
        
        # Calculate overall score
        overall_score = self._calculate_overall_score(normalized_scores)
        
        # Create domain summary
        domain_summary = self._create_domain_summary(worker_results, normalized_scores)
        
        # Identify failures
        critical_failures, non_critical_failures = self._categorize_failures(worker_results)
        
        # Apply policy to make release decision
        release_decision, release_rationale = self._apply_policy(
            worker_results,
            normalized_scores,
            overall_score,
            critical_failures,
            non_critical_failures,
        )
        
        return AggregatedResult(
            aggregation_id=aggregation_id,
            trial_id=trial_id,
            worker_results=worker_results,
            normalized_scores=normalized_scores,
            overall_score=overall_score,
            domain_summary=domain_summary,
            critical_failures=critical_failures,
            non_critical_failures=non_critical_failures,
            release_decision=release_decision,
            release_rationale=release_rationale,
            policy_version=self.policy_version,
            # Architecture-compliant fields
            deterministic_grades={
                "passed": sum(1 for r in worker_results.values() if r.passed and r.grader_mode.value == "deterministic"),
                "failed": sum(1 for r in worker_results.values() if not r.passed and r.grader_mode.value == "deterministic"),
            },
            ai_grades={
                "evaluated": sum(1 for r in worker_results.values() if r.grader_mode.value == "model_judge"),
                "skipped": sum(1 for r in worker_results.values() if r.grader_mode.value != "model_judge"),
            },
            token_usage={
                "live_tokens": 0,  # Would be populated from execution context
                "evaluation_tokens": sum(r.judge_cost_usd for r in worker_results.values()),
                "mode": "replay",  # Would be populated from execution context
            },
            blocking_trials=[
                f["worker_type"] for f in critical_failures
            ],
        )
    
    def _normalize_scores(
        self, worker_results: dict[WorkerType, WorkerResult]
    ) -> dict[WorkerType, float]:
        """Normalize scores from different workers."""
        normalized = {}
        
        for worker_type, result in worker_results.items():
            # Score is already normalized to [0,1] in WorkerResult
            normalized[worker_type] = result.score
        
        # Ensure all expected worker types have a score (use 0 if missing)
        expected_types = [
            WorkerType.TOOL_POLICY,
            WorkerType.RETRIEVAL_QUALITY,
            WorkerType.GRAPH_COMPLIANCE,
            WorkerType.OUTPUT_QUALITY,
            WorkerType.SECURITY,
            WorkerType.PERFORMANCE,
        ]
        
        for worker_type in expected_types:
            if worker_type not in normalized:
                normalized[worker_type] = 0.0
        
        return normalized
    
    def _calculate_overall_score(
        self, normalized_scores: dict[WorkerType, float]
    ) -> float:
        """Calculate weighted overall score."""
        overall = (
            normalized_scores.get(WorkerType.TOOL_POLICY, 0.0) * self.policy.tool_weight +
            normalized_scores.get(WorkerType.RETRIEVAL_QUALITY, 0.0) * self.policy.retrieval_weight +
            normalized_scores.get(WorkerType.GRAPH_COMPLIANCE, 0.0) * self.policy.graph_weight +
            normalized_scores.get(WorkerType.OUTPUT_QUALITY, 0.0) * self.policy.output_weight +
            normalized_scores.get(WorkerType.SECURITY, 0.0) * self.policy.security_weight +
            normalized_scores.get(WorkerType.PERFORMANCE, 0.0) * self.policy.performance_weight
        )
        
        return round(overall, 3)
    
    def _create_domain_summary(
        self,
        worker_results: dict[WorkerType, WorkerResult],
        normalized_scores: dict[WorkerType, float],
    ) -> dict[str, dict[str, Any]]:
        """Create per-domain summary."""
        summary = {}
        
        for worker_type, result in worker_results.items():
            summary[worker_type.value] = {
                "score": result.score,
                "normalized_score": normalized_scores[worker_type],
                "passed": result.passed,
                "severity": result.severity.value,
                "reason_code": result.reason_code,
                "reason_message": result.reason_message,
                "worker_version": result.worker_version,
                "grader_mode": result.grader_mode.value,
                "confidence": result.confidence,
            }
        
        return summary
    
    def _categorize_failures(
        self, worker_results: dict[WorkerType, WorkerResult]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Categorize failures into critical and non-critical."""
        critical = []
        non_critical = []
        
        for worker_type, result in worker_results.items():
            if result.passed:
                continue
            
            failure_info = {
                "worker_type": worker_type.value,
                "reason_code": result.reason_code,
                "reason_message": result.reason_message,
                "severity": result.severity.value,
                "score": result.score,
            }
            
            if result.severity in (Severity.CRITICAL, Severity.ERROR):
                critical.append(failure_info)
            else:
                non_critical.append(failure_info)
        
        return critical, non_critical
    
    def _apply_policy(
        self,
        worker_results: dict[WorkerType, WorkerResult],
        normalized_scores: dict[WorkerType, float],
        overall_score: float,
        critical_failures: list[dict[str, Any]],
        non_critical_failures: list[dict[str, Any]],
    ) -> tuple[ReleaseDecision, str]:
        """Apply policy to make release decision matching the architecture."""
        
        # CRITICAL: Block on critical security failures
        if (self.policy.block_on_critical_security and
            any(f["worker_type"] == WorkerType.SECURITY.value for f in critical_failures)):
            return (
                ReleaseDecision.BLOCKED,
                "critical_security_regression"
            )
        
        # CRITICAL: Block on critical tool failures
        if (self.policy.block_on_critical_tool and
            any(f["worker_type"] == WorkerType.TOOL_POLICY.value for f in critical_failures)):
            return (
                ReleaseDecision.BLOCKED,
                "critical_tool_regression"
            )
        
        # CRITICAL: Block on critical graph failures
        if (self.policy.block_on_critical_graph and
            any(f["worker_type"] == WorkerType.GRAPH_COMPLIANCE.value for f in critical_failures)):
            return (
                ReleaseDecision.BLOCKED,
                "critical_graph_regression"
            )
        
        # Block on any other critical failures
        if critical_failures:
            return (
                ReleaseDecision.BLOCKED,
                "critical_failures_detected"
            )
        
        # Check minimum score thresholds per domain
        if normalized_scores.get(WorkerType.TOOL_POLICY, 0.0) < self.policy.minimum_tool_score:
            return (
                ReleaseDecision.BLOCKED,
                "tool_score_below_threshold"
            )
        
        if normalized_scores.get(WorkerType.RETRIEVAL_QUALITY, 0.0) < self.policy.minimum_retrieval_score:
            return (
                ReleaseDecision.BLOCKED,
                "retrieval_score_below_threshold"
            )
        
        if normalized_scores.get(WorkerType.GRAPH_COMPLIANCE, 0.0) < self.policy.minimum_graph_score:
            return (
                ReleaseDecision.BLOCKED,
                "graph_score_below_threshold"
            )
        
        if normalized_scores.get(WorkerType.OUTPUT_QUALITY, 0.0) < self.policy.minimum_output_score:
            return (
                ReleaseDecision.BLOCKED,
                "output_score_below_threshold"
            )
        
        if normalized_scores.get(WorkerType.PERFORMANCE, 0.0) < self.policy.minimum_performance_score:
            return (
                ReleaseDecision.BLOCKED,
                "p95_latency_regression"
            )
        
        # Check overall score threshold
        if overall_score < self.policy.minimum_overall_score:
            return (
                ReleaseDecision.BLOCKED,
                "overall_score_below_threshold"
            )
        
        # Check non-critical failure tolerance
        if len(non_critical_failures) > self.policy.max_non_critical_failures:
            return (
                ReleaseDecision.INCONCLUSIVE,
                "exceeded_non_critical_failure_tolerance"
            )
        
        # Conditional/inconclusive if there are some non-critical failures
        if non_critical_failures and self.policy.allow_conditional_approval:
            return (
                ReleaseDecision.INCONCLUSIVE,
                "non_critical_failures_present"
            )
        
        # Full approval
        return (
            ReleaseDecision.PASSED,
            "all_policy_checks_passed"
        )
    
    def _get_failure_summary(self, failures: list[dict[str, Any]]) -> str:
        """Get a summary of failures."""
        if not failures:
            return "none"
        
        summaries = []
        for failure in failures[:3]:  # Limit to first 3
            summaries.append(
                f"{failure['worker_type']}: {failure['reason_code']}"
            )
        
        if len(failures) > 3:
            summaries.append(f"and {len(failures) - 3} more")
        
        return "; ".join(summaries)
    
    def update_policy(self, policy: AggregationPolicy) -> None:
        """Update the aggregation policy."""
        self.policy = policy
        self.policy.validate_weights()
