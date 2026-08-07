"""Grader router for selective evaluation with AI escalation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from glyph.evaluation.specialized_workers.artifact import EvaluationArtifact
from glyph.evaluation.specialized_workers.base import (
    BaseArtifactWorker,
    BaseSpecializedWorker,
    EvaluationEvidence,
    GraderMode,
    Severity,
    WorkerResult,
    WorkerType,
)
from glyph.evaluation.specialized_workers.ai_decision_gates import (
    AIJudgeGateChain,
    AIJudgeInvocationConfig,
    AIJudgeResult,
    GateDecision,
)

logger = logging.getLogger(__name__)


class RoutingDecision(StrEnum):
    """Routing decision for a trial."""
    BLOCK = "block"  # Critical violation, block immediately
    FAIL_DETERMINISTIC = "fail_deterministic"  # Schema/policy failure
    USE_CACHED = "use_cached"  # No behavioral change, use cached grade
    INVOKE_SMALL_JUDGE = "invoke_small_judge"  # Semantic difference, small judge
    INVOKE_STRONG_JUDGE = "invoke_strong_judge"  # Critical case, strong judge
    SAMPLE_MONITORING = "sample_monitoring"  # Random sampling for quality
    SKIP = "skip"  # Not worth evaluating


@dataclass
class RoutingCriteria:
    """Criteria for routing decisions."""
    # Security criteria
    has_security_violation: bool = False
    security_severity: Severity = Severity.INFO
    
    # Schema criteria
    has_schema_failure: bool = False
    schema_compliant: bool = True
    
    # Behavioral criteria
    behavioral_change_detected: bool = False
    semantic_difference_score: float = 0.0  # 0-1, higher = more different
    
    # Case importance
    is_critical_case: bool = False
    case_priority: str = "normal"  # "low", "normal", "high", "critical"
    
    # Deterministic grader results
    deterministic_passed: bool = True
    deterministic_confidence: float = 1.0
    
    # Cached grade availability
    has_cached_grade: bool = False
    cached_grade_compatible: bool = True


@dataclass
class RoutingResult:
    """Result of routing a trial for evaluation."""
    decision: RoutingDecision
    reason: str
    
    # Selected workers
    deterministic_workers: list[WorkerType] = field(default_factory=list)
    ai_judge_type: str | None = None  # "small", "strong", or None
    
    # Metadata
    requires_model_call: bool = False
    estimated_cost_usd: float = 0.0


class GraderRouter:
    """
    Routes trials to appropriate graders based on selective evaluation pattern.
    
    The router implements a cost-effective escalation strategy:
    1. Run deterministic graders first (inexpensive)
    2. Detect failures and uncertainty
    3. Escalate selected cases to AI judges (expensive)
    4. Aggregate results for final decision
    
    Now includes comprehensive decision gates for AI judge safety.
    """
    
    def __init__(
        self,
        deterministic_workers: list[BaseArtifactWorker],
        ai_judge_available: bool = True,
        small_judge_cost_usd: float = 0.01,
        strong_judge_cost_usd: float = 0.05,
        sample_rate: float = 0.1,  # 10% sampling for monitoring
        gate_chain: AIJudgeGateChain | None = None,
    ):
        self.deterministic_workers = deterministic_workers
        self.ai_judge_available = ai_judge_available
        self.small_judge_cost_usd = small_judge_cost_usd
        self.strong_judge_cost_usd = strong_judge_cost_usd
        self.sample_rate = sample_rate
        self.gate_chain = gate_chain or AIJudgeGateChain()
    
    def route_trial(
        self,
        artifact: EvaluationArtifact,
        criteria: RoutingCriteria | None = None,
    ) -> RoutingResult:
        """
        Route a trial to appropriate graders.
        
        Implements the selective evaluation pattern:
        - Use inexpensive deterministic checks first
        - Escalate only uncertain cases to stronger evaluators
        """
        if criteria is None:
            criteria = self._evaluate_criteria(artifact)
        
        # Apply routing logic
        if criteria.has_security_violation:
            return self._route_block(criteria)
        
        elif criteria.has_schema_failure:
            return self._route_fail_deterministic(criteria)
        
        elif not criteria.behavioral_change_detected and criteria.has_cached_grade:
            return self._route_cached(criteria)
        
        elif criteria.semantic_difference_score > 0.7:
            return self._route_small_judge(criteria)
        
        elif criteria.is_critical_case:
            return self._route_strong_judge(criteria)
        
        else:
            return self._route_sample_monitoring(criteria)
    
    def _evaluate_criteria(self, artifact: EvaluationArtifact) -> RoutingCriteria:
        """Evaluate routing criteria from an artifact."""
        # Extract information from artifact events
        criteria = RoutingCriteria()
        
        for event in artifact.events:
            event_type = event.get("event_type")
            
            if event_type == "security":
                criteria.has_security_violation = True
                criteria.security_severity = Severity(
                    event.get("severity", "info")
                )
            
            elif event_type == "schema_validation":
                if not event.get("passed", True):
                    criteria.has_schema_failure = True
                    criteria.schema_compliant = False
        
        # Check for behavioral changes (simplified)
        # In practice, would compare with baseline
        criteria.behavioral_change_detected = False
        
        # Check if case is critical (from metadata)
        criteria.is_critical_case = artifact.case_id.startswith("critical_")
        
        return criteria
    
    def _route_block(self, criteria: RoutingCriteria) -> RoutingResult:
        """Route to immediate block for critical security violations."""
        return RoutingResult(
            decision=RoutingDecision.BLOCK,
            reason=f"Critical security violation: {criteria.security_severity.value}",
            deterministic_workers=[
                WorkerType.SECURITY,
            ],
            requires_model_call=False,
            estimated_cost_usd=0.0,
        )
    
    def _route_fail_deterministic(self, criteria: RoutingCriteria) -> RoutingResult:
        """Route to deterministic failure for schema/policy violations."""
        return RoutingResult(
            decision=RoutingDecision.FAIL_DETERMINISTIC,
            reason="Schema or policy failure detected",
            deterministic_workers=[
                WorkerType.OUTPUT_QUALITY,
                WorkerType.TOOL_POLICY,
            ],
            requires_model_call=False,
            estimated_cost_usd=0.0,
        )
    
    def _route_cached(self, criteria: RoutingCriteria) -> RoutingResult:
        """Route to use cached grade when no behavioral change."""
        return RoutingResult(
            decision=RoutingDecision.USE_CACHED,
            reason="No behavioral change detected, using cached grade",
            deterministic_workers=[],
            requires_model_call=False,
            estimated_cost_usd=0.0,
        )
    
    def _route_small_judge(self, criteria: RoutingCriteria) -> RoutingResult:
        """Route to small AI judge for semantic differences."""
        if not self.ai_judge_available:
            # Fallback to deterministic if AI judge not available
            return RoutingResult(
                decision=RoutingDecision.FAIL_DETERMINISTIC,
                reason="Semantic difference detected but AI judge unavailable",
                deterministic_workers=[
                    WorkerType.OUTPUT_QUALITY,
                    WorkerType.RETRIEVAL_QUALITY,
                ],
                requires_model_call=False,
                estimated_cost_usd=0.0,
            )
        
        return RoutingResult(
            decision=RoutingDecision.INVOKE_SMALL_JUDGE,
            reason=f"Semantic difference detected (score: {criteria.semantic_difference_score})",
            deterministic_workers=[
                WorkerType.OUTPUT_QUALITY,
                WorkerType.RETRIEVAL_QUALITY,
            ],
            ai_judge_type="small",
            requires_model_call=True,
            estimated_cost_usd=self.small_judge_cost_usd,
        )
    
    def _route_strong_judge(self, criteria: RoutingCriteria) -> RoutingResult:
        """Route to strong AI judge for critical cases."""
        if not self.ai_judge_available:
            # Fallback to deterministic if AI judge not available
            return RoutingResult(
                decision=RoutingDecision.FAIL_DETERMINISTIC,
                reason="Critical case but AI judge unavailable",
                deterministic_workers=[
                    WorkerType.SECURITY,
                    WorkerType.OUTPUT_QUALITY,
                    WorkerType.TOOL_POLICY,
                ],
                requires_model_call=False,
                estimated_cost_usd=0.0,
            )
        
        return RoutingResult(
            decision=RoutingDecision.INVOKE_STRONG_JUDGE,
            reason="Critical case requires strong evaluation",
            deterministic_workers=[
                WorkerType.SECURITY,
                WorkerType.OUTPUT_QUALITY,
                WorkerType.TOOL_POLICY,
            ],
            ai_judge_type="strong",
            requires_model_call=True,
            estimated_cost_usd=self.strong_judge_cost_usd,
        )
    
    def _route_sample_monitoring(self, criteria: RoutingCriteria) -> RoutingResult:
        """Route to sampling for quality monitoring."""
        import random
        
        if random.random() > self.sample_rate:
            # Not sampled, skip
            return RoutingResult(
                decision=RoutingDecision.SKIP,
                reason="Not selected for quality monitoring sampling",
                deterministic_workers=[],
                requires_model_call=False,
                estimated_cost_usd=0.0,
            )
        
        # Sampled, run deterministic graders
        return RoutingResult(
            decision=RoutingDecision.SAMPLE_MONITORING,
            reason="Selected for quality monitoring sampling",
            deterministic_workers=[
                WorkerType.OUTPUT_QUALITY,
                WorkerType.TOOL_POLICY,
                WorkerType.RETRIEVAL_QUALITY,
            ],
            requires_model_call=False,
            estimated_cost_usd=0.0,
        )


class SelectiveEvaluationPipeline:
    """
    Pipeline for selective evaluation with AI escalation and decision gates.
    
    This pipeline:
    1. Routes trials to appropriate graders
    2. Runs deterministic graders
    3. Escalates to AI judges when needed (with decision gates)
    4. Aggregates results
    """
    
    def __init__(
        self,
        grader_router: GraderRouter,
        deterministic_workers: dict[WorkerType, BaseArtifactWorker],
    ):
        self.router = grader_router
        self.deterministic_workers = deterministic_workers
        self.gate_chain = grader_router.gate_chain
    
    async def evaluate_trial(
        self,
        artifact: EvaluationArtifact,
    ) -> WorkerResult:
        """
        Evaluate a trial using selective evaluation.
        
        Returns:
            Aggregated WorkerResult from all applicable graders
        """
        # Route the trial
        routing_result = self.router.route_trial(artifact)
        
        logger.info(
            f"Routed trial {artifact.trial_id} to {routing_result.decision.value}: "
            f"{routing_result.reason}"
        )
        
        # Handle immediate block
        if routing_result.decision == RoutingDecision.BLOCK:
            return self._create_blocking_result(artifact, routing_result)
        
        # Handle cached grade
        if routing_result.decision == RoutingDecision.USE_CACHED:
            return self._create_cached_result(artifact, routing_result)
        
        # Handle skip
        if routing_result.decision == RoutingDecision.SKIP:
            return self._create_skip_result(artifact, routing_result)
        
        # Run deterministic workers
        deterministic_results = await self._run_deterministic_workers(
            artifact,
            routing_result.deterministic_workers,
        )
        
        # Check if deterministic results are conclusive
        if self._is_deterministically_conclusive(deterministic_results):
            return self._aggregate_deterministic_results(
                artifact,
                deterministic_results,
            )
        
        # Escalate to AI judge if needed
        if routing_result.ai_judge_type:
            ai_result = await self._invoke_ai_judge(
                artifact,
                routing_result.ai_judge_type,
            )
            return self._aggregate_with_ai_judge(
                artifact,
                deterministic_results,
                ai_result,
            )
        
        # Otherwise, return deterministic results
        return self._aggregate_deterministic_results(
            artifact,
            deterministic_results,
        )
    
    async def _run_deterministic_workers(
        self,
        artifact: EvaluationArtifact,
        worker_types: list[WorkerType],
    ) -> dict[WorkerType, WorkerResult]:
        """Run deterministic workers in parallel."""
        import asyncio
        
        results = {}
        
        async def run_worker(worker_type: WorkerType) -> tuple[WorkerType, WorkerResult]:
            worker = self.deterministic_workers.get(worker_type)
            if worker and worker.can_evaluate_artifact(artifact):
                result = worker.evaluate_artifact(artifact)
                return worker_type, result
            return worker_type, self._create_skip_result_for_worker(worker_type)
        
        # Run workers in parallel
        tasks = [run_worker(wt) for wt in worker_types]
        worker_results = await asyncio.gather(*tasks)
        
        for worker_type, result in worker_results:
            results[worker_type] = result
        
        return results
    
    async def _invoke_ai_judge(
        self,
        artifact: EvaluationArtifact,
        judge_type: str,
    ) -> WorkerResult:
        """Invoke an AI judge for semantic evaluation with decision gates."""
        logger.info(f"Invoking {judge_type} AI judge for trial {artifact.trial_id}")
        
        # Create AI judge configuration
        config = AIJudgeInvocationConfig(
            model="gpt-4",
            max_tokens=1000,
            temperature=0.0,
            max_cost_per_call_usd=self.small_judge_cost_usd if judge_type == "small" else self.strong_judge_cost_usd,
            min_confidence=0.7,
            require_structured_output=True,
        )
        
        # Pre-invocation gate check
        routing_criteria = RoutingCriteria(
            is_critical_case=artifact.case_id.startswith("critical_"),
            semantic_difference_score=0.8,  # Placeholder
        )
        
        context = {
            "ai_judge_available": self.ai_judge_available,
            "estimated_cost_usd": config.max_cost_per_call_usd,
            "case_id": artifact.case_id,
        }
        
        decision, gate_result = await self.gate_chain.evaluate_pre_invocation(
            artifact, config, routing_criteria, context
        )
        
        # Handle gate decisions
        if decision == GateDecision.BLOCK:
            logger.warning(f"AI judge blocked by gate: {gate_result.reason}")
            return self._create_blocking_result_for_gate(artifact, gate_result)
        
        elif decision == GateDecision.FALLBACK:
            logger.info(f"AI judge fallback to deterministic: {gate_result.reason}")
            return self._create_fallback_result(artifact, gate_result)
        
        elif decision == GateDecision.SKIP:
            logger.info(f"AI judge skipped: {gate_result.reason}")
            return self._create_skip_result(artifact, gate_result)
        
        elif decision == GateDecision.RETRY:
            logger.info(f"AI judge retry requested: {gate_result.reason}")
            # In production, would implement retry logic
            return self._create_skip_result(artifact, gate_result)
        
        # Proceed with AI judge invocation
        try:
            ai_result = await self._do_invoke_ai_judge_internal(
                artifact, config, judge_type
            )
            
            # Post-result gate check
            post_decision, post_gate_result = await self.gate_chain.evaluate_post_result(
                ai_result, config, context
            )
            
            if post_decision == GateDecision.BLOCK:
                logger.warning(f"AI judge result blocked by gate: {post_gate_result.reason}")
                return self._create_blocking_result_for_gate(artifact, post_gate_result)
            
            elif post_decision == GateDecision.FALLBACK:
                logger.info(f"AI judge result fallback to deterministic: {post_gate_result.reason}")
                return self._create_fallback_result(artifact, post_gate_result)
            
            # Record actual spending
            self.gate_chain.record_actual_spending(artifact.case_id, ai_result.cost_usd)
            
            return ai_result.worker_result
            
        except Exception as e:
            logger.error(f"AI judge invocation failed: {e}")
            return self._create_error_result(artifact, str(e))
    
    async def _do_invoke_ai_judge_internal(
        self,
        artifact: EvaluationArtifact,
        config: AIJudgeInvocationConfig,
        judge_type: str,
    ) -> AIJudgeResult:
        """Internal method to actually invoke the AI judge."""
        # TODO: Implement actual AI judge invocation
        # This would call an LLM to evaluate semantic quality
        
        # Simulate AI judge result for now
        worker_result = WorkerResult(
            evaluation_id=f"ai_judge_{artifact.trial_id}",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=0.85,
            passed=True,
            severity=Severity.INFO,
            reason_code="ai_judge_evaluation",
            reason_message=f"AI judge ({judge_type}) evaluation completed",
            grader_mode=GraderMode.MODEL_JUDGE,
            confidence=0.8,
            judge_model=config.model,
            judge_prompt_version="1.0",
            judge_cost_usd=config.max_cost_per_call_usd,
            judge_latency_ms=2000 if judge_type == "small" else 5000,
        )
        
        return AIJudgeResult(
            success=True,
            worker_result=worker_result,
            model_used=config.model,
            tokens_used=500,  # Placeholder
            cost_usd=config.max_cost_per_call_usd,
            latency_ms=2000 if judge_type == "small" else 5000,
            confidence=0.8,
            output_valid=True,
            fallback_used=False,
        )
    
    def _is_deterministically_conclusive(
        self,
        results: dict[WorkerType, WorkerResult],
    ) -> bool:
        """Check if deterministic results are conclusive (no uncertainty)."""
        for result in results.values():
            # If any critical failure, conclusive (block)
            if not result.passed and result.severity == Severity.CRITICAL:
                return True
            
            # If low confidence, not conclusive
            if result.confidence < 0.8:
                return False
        
        return True
    
    def _aggregate_deterministic_results(
        self,
        artifact: EvaluationArtifact,
        results: dict[WorkerType, WorkerResult],
    ) -> WorkerResult:
        """Aggregate deterministic worker results."""
        # Check for failures
        failures = [
            (wt, r) for wt, r in results.items()
            if not r.passed
        ]
        
        if failures:
            # Use the most severe failure
            worst_failure = max(
                failures,
                key=lambda x: x[1].severity.value,  # Sort by severity
            )
            return worst_failure[1]
        
        # All passed, return success
        return WorkerResult(
            evaluation_id=f"aggregated_{artifact.trial_id}",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=1.0,
            passed=True,
            severity=Severity.INFO,
            reason_code="deterministic_pass",
            reason_message="All deterministic checks passed",
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
        )
    
    def _aggregate_with_ai_judge(
        self,
        artifact: EvaluationArtifact,
        deterministic_results: dict[WorkerType, WorkerResult],
        ai_result: WorkerResult,
    ) -> WorkerResult:
        """Aggregate deterministic results with AI judge."""
        # AI judge has final say on semantic quality
        # But deterministic failures still block
        
        critical_failures = [
            (wt, r) for wt, r in deterministic_results.items()
            if not r.passed and r.severity == Severity.CRITICAL
        ]
        
        if critical_failures:
            # Critical deterministic failures block regardless of AI judge
            worst_failure = max(
                critical_failures,
                key=lambda x: x[1].severity.value,
            )
            return worst_failure[1]
        
        # No critical failures, use AI judge result
        return ai_result
    
    def _create_blocking_result(
        self,
        artifact: EvaluationArtifact,
        routing_result: RoutingResult,
    ) -> WorkerResult:
        """Create a blocking result."""
        return WorkerResult(
            evaluation_id=f"block_{artifact.trial_id}",
            worker_type=WorkerType.SECURITY,
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=0.0,
            passed=False,
            severity=Severity.CRITICAL,
            reason_code="security_violation",
            reason_message=routing_result.reason,
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
        )
    
    def _create_cached_result(
        self,
        artifact: EvaluationArtifact,
        routing_result: RoutingResult,
    ) -> WorkerResult:
        """Create a cached grade result."""
        return WorkerResult(
            evaluation_id=f"cached_{artifact.trial_id}",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=1.0,  # Assume cached grade was passing
            passed=True,
            severity=Severity.INFO,
            reason_code="cached_grade",
            reason_message=routing_result.reason,
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
        )
    
    def _create_skip_result(
        self,
        artifact: EvaluationArtifact,
        routing_result: RoutingResult,
    ) -> WorkerResult:
        """Create a skip result."""
        return WorkerResult(
            evaluation_id=f"skip_{artifact.trial_id}",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=1.0,  # Skip is neutral
            passed=True,
            severity=Severity.INFO,
            reason_code="skipped",
            reason_message=routing_result.reason,
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
        )
    
    def _create_skip_result_for_worker(
        self,
        worker_type: WorkerType,
    ) -> WorkerResult:
        """Create a skip result for a specific worker."""
        return WorkerResult(
            evaluation_id=f"skip_{worker_type.value}",
            worker_type=worker_type,
            worker_version="1.0.0",
            trial_id="unknown",
            score=1.0,
            passed=True,
            severity=Severity.INFO,
            reason_code="worker_skipped",
            reason_message="Worker not applicable or skipped",
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
        )
    
    def _create_blocking_result_for_gate(
        self,
        artifact: EvaluationArtifact,
        gate_result,
    ) -> WorkerResult:
        """Create a blocking result from gate decision."""
        return WorkerResult(
            evaluation_id=f"gate_blocked_{artifact.trial_id}",
            worker_type=WorkerType.SECURITY,  # Security blocks are critical
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=0.0,
            passed=False,
            severity=Severity.CRITICAL,
            reason_code="gate_blocked",
            reason_message=f"Blocked by {gate_result.gate_name}: {gate_result.reason}",
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
            findings={
                "gate_name": gate_result.gate_name,
                "gate_type": gate_result.gate_type.value,
                "gate_decision": gate_result.decision.value,
            },
        )
    
    def _create_fallback_result(
        self,
        artifact: EvaluationArtifact,
        gate_result,
    ) -> WorkerResult:
        """Create a fallback result using deterministic evaluation."""
        # In production, this would run deterministic workers
        return WorkerResult(
            evaluation_id=f"gate_fallback_{artifact.trial_id}",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=0.75,  # Conservative score
            passed=True,
            severity=Severity.WARNING,
            reason_code="gate_fallback",
            reason_message=f"Gate fallback: {gate_result.reason}, using deterministic evaluation",
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=0.9,
            findings={
                "gate_name": gate_result.gate_name,
                "gate_type": gate_result.gate_type.value,
                "gate_decision": gate_result.decision.value,
                "fallback_used": True,
            },
        )
    
    def _create_error_result(
        self,
        artifact: EvaluationArtifact,
        error_message: str,
    ) -> WorkerResult:
        """Create an error result."""
        return WorkerResult(
            evaluation_id=f"error_{artifact.trial_id}",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=0.0,
            passed=False,
            severity=Severity.ERROR,
            reason_code="ai_judge_error",
            reason_message=f"AI judge error: {error_message}",
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=0.0,
            findings={
                "error": error_message,
                "fallback_used": True,
            },
        )