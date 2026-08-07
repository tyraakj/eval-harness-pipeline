"""Performance evaluator for specialized evaluation."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from glyph.evaluation.specialized_workers.base import (
    BaseArtifactWorker,
    BaseSpecializedWorker,
    EvaluationEvidence,
    GraderMode,
    Severity,
    WorkerResult,
    WorkerType,
)
from glyph.evaluation.specialized_workers.artifact import EvaluationArtifact


@dataclass
class PerformancePolicy:
    """Policy configuration for performance evaluation."""
    # Latency thresholds
    max_total_latency_ms: float = 30000  # 30 seconds
    max_time_to_first_token_ms: float = 5000  # 5 seconds
    avg_node_latency_ms: float = 1000  # 1 second per node
    
    # Token usage thresholds
    max_input_tokens: int = 100_000
    max_output_tokens: int = 10_000
    max_total_tokens: int = 110_000
    
    # Cost thresholds
    max_cost_usd: float = 1.0
    max_cost_per_token_usd: float = 0.0001
    
    # Resource usage
    max_tool_calls: int = 20
    max_retries: int = 3
    max_memory_mb: int = 512
    
    # Efficiency metrics
    min_tokens_per_second: float = 10.0
    min_cost_efficiency_score: float = 0.5


@dataclass
class PerformanceAnalysis:
    """Analysis of performance metrics."""
    total_latency_ms: float
    time_to_first_token_ms: float
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float
    tool_call_count: int
    retry_count: int
    estimated_memory_mb: float
    tokens_per_second: float
    cost_per_token_usd: float
    latency_violations: list[str]
    token_violations: list[str]
    cost_violations: list[str]
    resource_violations: list[str]
    efficiency_violations: list[str]


class PerformanceEvaluator(BaseSpecializedWorker):
    """Evaluates performance metrics deterministically."""
    
    def __init__(self, version: str = "1.0.0", policy: PerformancePolicy | None = None):
        super().__init__(version)
        self.policy = policy or PerformancePolicy()
    
    def _get_worker_type(self) -> WorkerType:
        return WorkerType.PERFORMANCE
    
    def can_evaluate(self, evidence: EvaluationEvidence) -> bool:
        """Can evaluate any evidence for performance metrics."""
        return True  # Performance evaluator should always run
    
    def evaluate(self, evidence: EvaluationEvidence) -> WorkerResult:
        """Evaluate performance metrics."""
        evaluation_id = str(uuid.uuid4())
        started_at = time.monotonic()
        
        # Analyze performance
        analysis = self._analyze_performance(evidence)
        
        # Aggregate findings
        findings = self._aggregate_findings(analysis, evidence)
        
        # Determine overall score and pass/fail
        score, passed, severity, reason_code, reason_message = self._compute_result(
            analysis, findings
        )
        
        # Generate evidence references
        evidence_refs = ["performance_metrics"]
        
        evaluation_duration_ms = int((time.monotonic() - started_at) * 1000)
        
        return self.create_result(
            evaluation_id=evaluation_id,
            trial_id=evidence.trial_id,
            score=score,
            passed=passed,
            severity=severity,
            reason_code=reason_code,
            reason_message=reason_message,
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
            evidence_refs=evidence_refs,
            findings=findings,
            evaluation_duration_ms=evaluation_duration_ms,
        )
    
    def _analyze_performance(self, evidence: EvaluationEvidence) -> PerformanceAnalysis:
        """Analyze performance metrics."""
        # Extract latency information
        total_latency_ms = evidence.latency_ms
        time_to_first_token_ms = self._extract_time_to_first_token(evidence)
        
        # Extract token usage
        input_tokens = evidence.token_usage.get("input_tokens", 0)
        output_tokens = evidence.token_usage.get("output_tokens", 0)
        total_tokens = input_tokens + output_tokens
        
        # Extract cost
        cost_usd = evidence.cost_usd
        
        # Count tool calls and retries
        tool_call_count = len(evidence.tool_calls)
        retry_count = self._count_retries(evidence)
        
        # Estimate memory usage
        estimated_memory_mb = self._estimate_memory_usage(evidence)
        
        # Calculate efficiency metrics
        tokens_per_second = self._calculate_tokens_per_second(
            total_tokens, total_latency_ms
        )
        cost_per_token_usd = (
            cost_usd / total_tokens if total_tokens > 0 else 0.0
        )
        
        # Check for violations
        latency_violations = self._check_latency_violations(
            total_latency_ms, time_to_first_token_ms, evidence
        )
        token_violations = self._check_token_violations(
            input_tokens, output_tokens, total_tokens
        )
        cost_violations = self._check_cost_violations(cost_usd, cost_per_token_usd)
        resource_violations = self._check_resource_violations(
            tool_call_count, retry_count, estimated_memory_mb
        )
        efficiency_violations = self._check_efficiency_violations(
            tokens_per_second, cost_per_token_usd
        )
        
        return PerformanceAnalysis(
            total_latency_ms=total_latency_ms,
            time_to_first_token_ms=time_to_first_token_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            tool_call_count=tool_call_count,
            retry_count=retry_count,
            estimated_memory_mb=estimated_memory_mb,
            tokens_per_second=tokens_per_second,
            cost_per_token_usd=cost_per_token_usd,
            latency_violations=latency_violations,
            token_violations=token_violations,
            cost_violations=cost_violations,
            resource_violations=resource_violations,
            efficiency_violations=efficiency_violations,
        )
    
    def _extract_time_to_first_token(self, evidence: EvaluationEvidence) -> float:
        """Extract time to first token from timestamps."""
        # Look for first token timestamp in metadata
        timestamps = evidence.timestamps
        if "first_token" in timestamps and "start" in timestamps:
            return (timestamps["first_token"] - timestamps["start"]).total_seconds() * 1000
        return 0.0  # Not available
    
    def _count_retries(self, evidence: EvaluationEvidence) -> int:
        """Count retry attempts."""
        retry_count = 0
        seen_tools = set()
        
        for call in evidence.tool_calls:
            tool_name = call.get("tool_name")
            if tool_name in seen_tools:
                retry_count += 1
            seen_tools.add(tool_name)
        
        return retry_count
    
    def _estimate_memory_usage(self, evidence: EvaluationEvidence) -> float:
        """Estimate memory usage based on tokens and context."""
        # Rough estimation: 1 token ≈ 4 bytes, plus overhead
        total_tokens = (
            evidence.token_usage.get("input_tokens", 0) +
            evidence.token_usage.get("output_tokens", 0)
        )
        base_memory = total_tokens * 4 / 1024 / 1024  # Convert to MB
        
        # Add overhead for tool calls and graph state
        overhead = len(evidence.tool_calls) * 0.5 + len(evidence.graph_nodes) * 0.1
        
        return base_memory + overhead
    
    def _calculate_tokens_per_second(
        self, total_tokens: int, latency_ms: float
    ) -> float:
        """Calculate tokens per second."""
        if latency_ms <= 0:
            return 0.0
        return (total_tokens / latency_ms) * 1000
    
    def _check_latency_violations(
        self, total_latency_ms: float, time_to_first_token_ms: float, evidence: EvaluationEvidence
    ) -> list[str]:
        """Check for latency violations."""
        violations = []
        
        if total_latency_ms > self.policy.max_total_latency_ms:
            violations.append(
                f"Total latency {total_latency_ms:.0f}ms exceeds limit {self.policy.max_total_latency_ms}ms"
            )
        
        if time_to_first_token_ms > self.policy.max_time_to_first_token_ms:
            violations.append(
                f"Time to first token {time_to_first_token_ms:.0f}ms exceeds limit {self.policy.max_time_to_first_token_ms}ms"
            )
        
        # Check average node latency
        if evidence.graph_nodes:
            avg_node_latency = total_latency_ms / len(evidence.graph_nodes)
            if avg_node_latency > self.policy.avg_node_latency_ms:
                violations.append(
                    f"Average node latency {avg_node_latency:.0f}ms exceeds limit {self.policy.avg_node_latency_ms}ms"
                )
        
        return violations
    
    def _check_token_violations(
        self, input_tokens: int, output_tokens: int, total_tokens: int
    ) -> list[str]:
        """Check for token usage violations."""
        violations = []
        
        if input_tokens > self.policy.max_input_tokens:
            violations.append(
                f"Input tokens {input_tokens} exceeds limit {self.policy.max_input_tokens}"
            )
        
        if output_tokens > self.policy.max_output_tokens:
            violations.append(
                f"Output tokens {output_tokens} exceeds limit {self.policy.max_output_tokens}"
            )
        
        if total_tokens > self.policy.max_total_tokens:
            violations.append(
                f"Total tokens {total_tokens} exceeds limit {self.policy.max_total_tokens}"
            )
        
        return violations
    
    def _check_cost_violations(self, cost_usd: float, cost_per_token_usd: float) -> list[str]:
        """Check for cost violations."""
        violations = []
        
        if cost_usd > self.policy.max_cost_usd:
            violations.append(
                f"Cost ${cost_usd:.4f} exceeds limit ${self.policy.max_cost_usd:.4f}"
            )
        
        if cost_per_token_usd > self.policy.max_cost_per_token_usd:
            violations.append(
                f"Cost per token ${cost_per_token_usd:.6f} exceeds limit ${self.policy.max_cost_per_token_usd:.6f}"
            )
        
        return violations
    
    def _check_resource_violations(
        self, tool_call_count: int, retry_count: int, estimated_memory_mb: float
    ) -> list[str]:
        """Check for resource usage violations."""
        violations = []
        
        if tool_call_count > self.policy.max_tool_calls:
            violations.append(
                f"Tool calls {tool_call_count} exceeds limit {self.policy.max_tool_calls}"
            )
        
        if retry_count > self.policy.max_retries:
            violations.append(
                f"Retries {retry_count} exceeds limit {self.policy.max_retries}"
            )
        
        if estimated_memory_mb > self.policy.max_memory_mb:
            violations.append(
                f"Estimated memory {estimated_memory_mb:.1f}MB exceeds limit {self.policy.max_memory_mb}MB"
            )
        
        return violations
    
    def _check_efficiency_violations(
        self, tokens_per_second: float, cost_per_token_usd: float
    ) -> list[str]:
        """Check for efficiency violations."""
        violations = []
        
        if tokens_per_second < self.policy.min_tokens_per_second:
            violations.append(
                f"Tokens per second {tokens_per_second:.1f} below minimum {self.policy.min_tokens_per_second}"
            )
        
        # Calculate cost efficiency (inverse of cost per token, normalized)
        cost_efficiency = 1.0 / (cost_per_token_usd * 10000 + 1) if cost_per_token_usd > 0 else 1.0
        if cost_efficiency < self.policy.min_cost_efficiency_score:
            violations.append(
                f"Cost efficiency {cost_efficiency:.2f} below minimum {self.policy.min_cost_efficiency_score}"
            )
        
        return violations
    
    def _aggregate_findings(
        self, analysis: PerformanceAnalysis, evidence: EvaluationEvidence
    ) -> dict[str, Any]:
        """Aggregate performance analysis findings."""
        return {
            "total_latency_ms": analysis.total_latency_ms,
            "time_to_first_token_ms": analysis.time_to_first_token_ms,
            "input_tokens": analysis.input_tokens,
            "output_tokens": analysis.output_tokens,
            "total_tokens": analysis.total_tokens,
            "cost_usd": analysis.cost_usd,
            "tool_call_count": analysis.tool_call_count,
            "retry_count": analysis.retry_count,
            "estimated_memory_mb": analysis.estimated_memory_mb,
            "tokens_per_second": analysis.tokens_per_second,
            "cost_per_token_usd": analysis.cost_per_token_usd,
            "latency_violations": analysis.latency_violations,
            "token_violations": analysis.token_violations,
            "cost_violations": analysis.cost_violations,
            "resource_violations": analysis.resource_violations,
            "efficiency_violations": analysis.efficiency_violations,
            "total_violations": (
                len(analysis.latency_violations) +
                len(analysis.token_violations) +
                len(analysis.cost_violations) +
                len(analysis.resource_violations) +
                len(analysis.efficiency_violations)
            ),
        }
    
    def _compute_result(
        self, analysis: PerformanceAnalysis, findings: dict[str, Any]
    ) -> tuple[float, bool, Severity, str, str]:
        """Compute overall score and pass/fail result."""
        total_violations = findings["total_violations"]
        
        # Critical failures
        if analysis.cost_violations:
            return (
                0.0,
                False,
                Severity.ERROR,
                "cost_violations",
                f"Cost violations: {', '.join(analysis.cost_violations[:2])}"
            )
        
        if analysis.resource_violations:
            return (
                0.0,
                False,
                Severity.ERROR,
                "resource_violations",
                f"Resource violations: {', '.join(analysis.resource_violations[:2])}"
            )
        
        # High severity failures
        if analysis.latency_violations:
            return (
                0.5,
                False,
                Severity.WARNING,
                "latency_violations",
                f"Latency violations: {', '.join(analysis.latency_violations[:2])}"
            )
        
        if analysis.token_violations:
            return (
                0.6,
                False,
                Severity.WARNING,
                "token_violations",
                f"Token violations: {', '.join(analysis.token_violations[:2])}"
            )
        
        # Medium severity failures
        if analysis.efficiency_violations:
            return (
                0.7,
                False,
                Severity.INFO,
                "efficiency_violations",
                f"Efficiency violations: {', '.join(analysis.efficiency_violations[:2])}"
            )
        
        # Calculate performance score based on efficiency
        # Better performance = higher score
        latency_score = min(1.0, self.policy.max_total_latency_ms / (analysis.total_latency_ms + 1))
        cost_score = min(1.0, self.policy.max_cost_usd / (analysis.cost_usd + 0.0001))
        efficiency_score = min(1.0, analysis.tokens_per_second / self.policy.min_tokens_per_second)
        
        overall_score = (latency_score + cost_score + efficiency_score) / 3
        
        if overall_score >= 0.8:
            return (
                overall_score,
                True,
                Severity.INFO,
                "excellent_performance",
                f"Excellent performance (score: {overall_score:.2f})"
            )
        elif overall_score >= 0.6:
            return (
                overall_score,
                True,
                Severity.INFO,
                "good_performance",
                f"Good performance (score: {overall_score:.2f})"
            )
        else:
            return (
                overall_score,
                False,
                Severity.WARNING,
                "poor_performance",
                f"Poor performance (score: {overall_score:.2f})"
            )


class ArtifactPerformanceEvaluator(BaseArtifactWorker, PerformanceEvaluator):
    """Performance evaluator that works with immutable artifacts."""
    
    def __init__(self, version: str = "1.0.0", policy: PerformancePolicy | None = None):
        BaseArtifactWorker.__init__(self, version)
        PerformanceEvaluator.__init__(self, version, policy)
    
    def _get_worker_type(self) -> WorkerType:
        return WorkerType.PERFORMANCE
    
    def can_evaluate_artifact(self, artifact: EvaluationArtifact) -> bool:
        """Can evaluate any artifact for performance metrics."""
        return True  # Performance evaluator should always run
    
    def evaluate_artifact(self, artifact: EvaluationArtifact) -> WorkerResult:
        """Evaluate artifact by extracting evidence and delegating to base evaluator."""
        evidence = self.extract_evidence_from_artifact(artifact)
        return self.evaluate(evidence)
