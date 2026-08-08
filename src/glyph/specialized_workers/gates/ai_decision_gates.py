"""Decision gates for LLM-based workers with validation and fallback mechanisms."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from glyph.specialized_workers.base import (
    WorkerResult,
)

@dataclass
class RoutingCriteria:
    """Criteria used for routing evaluation tasks."""
    is_critical_case: bool = False
    semantic_difference_score: float = 0.0
    case_priority: str = "normal"

logger = logging.getLogger(__name__)


class GateDecision(StrEnum):
    """Decision from a decision gate."""
    PROCEED = "proceed"  # Allow the operation to proceed
    BLOCK = "block"  # Block the operation
    FALLBACK = "fallback"  # Use fallback mechanism
    RETRY = "retry"  # Retry with different parameters
    SKIP = "skip"  # Skip this operation


class GateType(StrEnum):
    """Type of decision gate."""
    PRE_INVOCATION = "pre_invocation"  # Before AI judge call
    POST_RESULT = "post_result"  # After AI judge returns
    COST_CONTROL = "cost_control"  # Budget and spending control
    QUALITY_CONTROL = "quality_control"  # Output quality validation
    CONFIDENCE_CONTROL = "confidence_control"  # Confidence threshold validation


@dataclass
class GateResult:
    """Result from a decision gate."""
    gate_type: GateType
    decision: GateDecision
    reason: str
    gate_name: str
    
    # Optional fallback data
    fallback_data: dict[str, Any] = field(default_factory=dict)
    
    # Timing
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int = 0
    
    # Blocking info
    is_blocking: bool = False
    can_retry: bool = False
    retry_after_seconds: int = 0


@dataclass
class AIJudgeInvocationConfig:
    """Configuration for AI judge invocation."""
    # Model selection
    model: str = "gpt-4"
    max_tokens: int = 1000
    temperature: float = 0.0
    
    # Timing
    timeout_seconds: int = 30
    max_retries: int = 2
    
    # Cost control
    max_cost_per_call_usd: float = 0.05
    max_total_cost_usd: float = 1.0
    
    # Quality requirements
    min_confidence: float = 0.7
    require_structured_output: bool = True
    allowed_reason_codes: set[str] = field(default_factory=set)
    prohibited_reason_codes: set[str] = field(default_factory=set)
    
    # Rate limiting
    calls_per_minute: int = 10
    calls_per_hour: int = 100


@dataclass
class AIJudgeResult:
    """Result from AI judge execution."""
    success: bool
    worker_result: WorkerResult | None = None
    error: str | None = None
    
    # Metadata
    model_used: str = ""
    tokens_used: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    
    # Quality metrics
    confidence: float = 0.0
    output_valid: bool = False
    fallback_used: bool = False


class DecisionGate:
    """Base class for decision gates."""
    
    def __init__(self, gate_name: str, enabled: bool = True):
        self.gate_name = gate_name
        self.enabled = enabled
    
    def evaluate(self, context: dict[str, Any]) -> GateResult:
        """Evaluate the gate conditions."""
        if not self.enabled:
            return GateResult(
                gate_type=self._get_gate_type(),
                decision=GateDecision.PROCEED,
                reason="Gate disabled",
                gate_name=self.gate_name,
            )
        
        return self._do_evaluate(context)
    
    def _get_gate_type(self) -> GateType:
        """Return the gate type."""
        raise NotImplementedError
    
    def _do_evaluate(self, context: dict[str, Any]) -> GateResult:
        """Perform the actual gate evaluation."""
        raise NotImplementedError


class PreInvocationGate(DecisionGate):
    """Gate that validates conditions before AI judge invocation."""
    
    def _get_gate_type(self) -> GateType:
        return GateType.PRE_INVOCATION
    
    def _do_evaluate(self, context: dict[str, Any]) -> GateResult:
        """Validate pre-invocation conditions."""
        artifact = context.get("artifact")
        config = context.get("config")
        routing_criteria = context.get("routing_criteria")
        
        # Check if artifact is suitable for AI evaluation
        if not self._is_artifact_suitable(artifact):
            return GateResult(
                gate_type=GateType.PRE_INVOCATION,
                decision=GateDecision.FALLBACK,
                reason="Artifact not suitable for AI evaluation",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check if AI judge is available
        if not context.get("ai_judge_available", False):
            return GateResult(
                gate_type=GateType.PRE_INVOCATION,
                decision=GateDecision.FALLBACK,
                reason="AI judge not available",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check budget constraints
        if not self._check_budget_constraints(context):
            return GateResult(
                gate_type=GateType.PRE_INVOCATION,
                decision=GateDecision.BLOCK,
                reason="Budget constraints exceeded",
                gate_name=self.gate_name,
                is_blocking=True,
            )
        
        # Check rate limiting
        if not self._check_rate_limiting(context):
            return GateResult(
                gate_type=GateType.PRE_INVOCATION,
                decision=GateDecision.RETRY,
                reason="Rate limit exceeded",
                gate_name=self.gate_name,
                can_retry=True,
                retry_after_seconds=60,
            )
        
        # Check if case is critical enough for AI evaluation
        if not self._is_case_critical_enough(routing_criteria):
            return GateResult(
                gate_type=GateType.PRE_INVOCATION,
                decision=GateDecision.SKIP,
                reason="Case not critical enough for AI evaluation",
                gate_name=self.gate_name,
            )
        
        return GateResult(
            gate_type=GateType.PRE_INVOCATION,
            decision=GateDecision.PROCEED,
            reason="All pre-invocation checks passed",
            gate_name=self.gate_name,
        )
    
    def _is_artifact_suitable(self, artifact) -> bool:
        """Check if artifact is suitable for AI evaluation."""
        if not artifact:
            return False
        
        # Check if artifact has sufficient data
        if not artifact.final_output:
            return False
        
        # Check if artifact is in valid state (accept pending and completed)
        status_value = artifact.status.value if hasattr(artifact.status, 'value') else str(artifact.status)
        if status_value not in ("pending", "completed"):
            return False
        
        return True
    
    def _check_budget_constraints(self, context: dict[str, Any]) -> bool:
        """Check if budget constraints allow AI evaluation."""
        spent_usd = context.get("total_spent_usd", 0.0)
        max_budget = context.get("max_budget_usd", 1.0)
        
        # Estimate cost of this call
        estimated_cost = context.get("estimated_cost_usd", 0.01)
        
        return (spent_usd + estimated_cost) <= max_budget
    
    def _check_rate_limiting(self, context: dict[str, Any]) -> bool:
        """Check if rate limiting allows this call."""
        # In production, this would check Redis or similar
        calls_this_minute = context.get("calls_this_minute", 0)
        max_calls = context.get("max_calls_per_minute", 10)
        
        return calls_this_minute < max_calls
    
    def _is_case_critical_enough(self, routing_criteria) -> bool:
        """Check if case is critical enough to warrant AI evaluation."""
        if not routing_criteria:
            return False
        
        # Critical cases always get AI evaluation
        if routing_criteria.is_critical_case:
            return True
        
        # High semantic difference warrants AI evaluation
        if routing_criteria.semantic_difference_score > 0.7:
            return True
        
        # Medium semantic difference for high priority cases
        if (routing_criteria.semantic_difference_score > 0.5 and
            routing_criteria.case_priority in ("high", "critical")):
            return True
        
        return False


class PostResultGate(DecisionGate):
    """Gate that validates AI judge results after execution."""
    
    def _get_gate_type(self) -> GateType:
        return GateType.POST_RESULT
    
    def _do_evaluate(self, context: dict[str, Any]) -> GateResult:
        """Validate post-result conditions."""
        ai_result = context.get("ai_result")
        config = context.get("config")
        
        if not ai_result or not ai_result.success:
            return GateResult(
                gate_type=GateType.POST_RESULT,
                decision=GateDecision.FALLBACK,
                reason="AI judge execution failed",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Validate result structure
        if not self._validate_result_structure(ai_result):
            return GateResult(
                gate_type=GateType.POST_RESULT,
                decision=GateDecision.FALLBACK,
                reason="AI judge result structure invalid",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check confidence threshold
        if not self._check_confidence_threshold(ai_result, config):
            return GateResult(
                gate_type=GateType.POST_RESULT,
                decision=GateDecision.FALLBACK,
                reason=f"AI judge confidence {ai_result.confidence} below threshold {config.min_confidence}",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check for prohibited reason codes
        if not self._check_reason_codes(ai_result, config):
            return GateResult(
                gate_type=GateType.POST_RESULT,
                decision=GateDecision.BLOCK,
                reason="AI judge returned prohibited reason code",
                gate_name=self.gate_name,
                is_blocking=True,
            )
        
        # Check if result contains required fields
        if not self._check_required_fields(ai_result):
            return GateResult(
                gate_type=GateType.POST_RESULT,
                decision=GateDecision.FALLBACK,
                reason="AI judge result missing required fields",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        return GateResult(
            gate_type=GateType.POST_RESULT,
            decision=GateDecision.PROCEED,
            reason="All post-result checks passed",
            gate_name=self.gate_name,
        )
    
    def _validate_result_structure(self, ai_result: AIJudgeResult) -> bool:
        """Validate that AI result has required structure."""
        if not ai_result.worker_result:
            return False
        
        result = ai_result.worker_result
        
        # Check required fields
        if not result.evaluation_id:
            return False
        if not result.worker_type:
            return False
        if not result.trial_id:
            return False
        if result.score is None:
            return False
        if result.passed is None:
            return False
        
        return True
    
    def _check_confidence_threshold(
        self, ai_result: AIJudgeResult, config: AIJudgeInvocationConfig
    ) -> bool:
        """Check if confidence meets minimum threshold."""
        return ai_result.confidence >= config.min_confidence
    
    def _check_reason_codes(
        self, ai_result: AIJudgeResult, config: AIJudgeInvocationConfig
    ) -> bool:
        """Check for prohibited reason codes."""
        if not ai_result.worker_result:
            return True
        
        result = ai_result.worker_result
        return result.reason_code not in config.prohibited_reason_codes
    
    def _check_required_fields(self, ai_result: AIJudgeResult) -> bool:
        """Check that result contains required fields."""
        result = ai_result.worker_result
        
        # Check that findings are present for debugging
        if not result.findings:
            return False
        
        # Check that reason message is present
        if not result.reason_message:
            return False
        
        return True


class CostControlGate(DecisionGate):
    """Gate that controls AI judge spending."""
    
    def __init__(
        self,
        gate_name: str = "cost_control",
        enabled: bool = True,
        max_total_spending_usd: float = 10.0,
        max_per_case_spending_usd: float = 0.5,
        alert_threshold_usd: float = 5.0,
    ):
        super().__init__(gate_name, enabled)
        self.max_total_spending_usd = max_total_spending_usd
        self.max_per_case_spending_usd = max_per_case_spending_usd
        self.alert_threshold_usd = alert_threshold_usd
        self._total_spent_usd = 0.0
        self._case_spending: dict[str, float] = {}
    
    def _get_gate_type(self) -> GateType:
        return GateType.COST_CONTROL
    
    def _do_evaluate(self, context: dict[str, Any]) -> GateResult:
        """Evaluate cost control conditions."""
        estimated_cost = context.get("estimated_cost_usd", 0.0)
        case_id = context.get("case_id", "")
        
        # Check total spending
        if (self._total_spent_usd + estimated_cost) > self.max_total_spending_usd:
            return GateResult(
                gate_type=GateType.COST_CONTROL,
                decision=GateDecision.BLOCK,
                reason=f"Total spending {self._total_spent_usd + estimated_cost} would exceed limit {self.max_total_spending_usd}",
                gate_name=self.gate_name,
                is_blocking=True,
            )
        
        # Check per-case spending
        case_spent = self._case_spending.get(case_id, 0.0)
        if (case_spent + estimated_cost) > self.max_per_case_spending_usd:
            return GateResult(
                gate_type=GateType.COST_CONTROL,
                decision=GateDecision.FALLBACK,
                reason=f"Case spending {case_spent + estimated_cost} would exceed limit {self.max_per_case_spending_usd}",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check alert threshold
        if (self._total_spent_usd + estimated_cost) > self.alert_threshold_usd:
            logger.warning(
                f"Cost alert: Spending {self._total_spent_usd + estimated_cost} "
                f"approaching limit {self.max_total_spending_usd}"
            )
        
        return GateResult(
            gate_type=GateType.COST_CONTROL,
            decision=GateDecision.PROCEED,
            reason="Cost control checks passed",
            gate_name=self.gate_name,
        )
    
    def record_spending(self, case_id: str, cost_usd: float):
        """Record actual spending after AI judge call."""
        self._total_spent_usd += cost_usd
        self._case_spending[case_id] = self._case_spending.get(case_id, 0.0) + cost_usd


class QualityControlGate(DecisionGate):
    """Gate that validates AI judge output quality."""
    
    def _get_gate_type(self) -> GateType:
        return GateType.QUALITY_CONTROL
    
    def _do_evaluate(self, context: dict[str, Any]) -> GateResult:
        """Validate quality control conditions."""
        ai_result = context.get("ai_result")
        
        if not ai_result or not ai_result.success:
            return GateResult(
                gate_type=GateType.QUALITY_CONTROL,
                decision=GateDecision.FALLBACK,
                reason="AI judge execution failed quality check",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check output validity
        if not ai_result.output_valid:
            return GateResult(
                gate_type=GateType.QUALITY_CONTROL,
                decision=GateDecision.FALLBACK,
                reason="AI judge output validation failed",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check for suspicious patterns
        if self._has_suspicious_patterns(ai_result):
            return GateResult(
                gate_type=GateType.QUALITY_CONTROL,
                decision=GateDecision.FALLBACK,
                reason="AI judge output contains suspicious patterns",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check result consistency
        if not self._check_result_consistency(ai_result):
            return GateResult(
                gate_type=GateType.QUALITY_CONTROL,
                decision=GateDecision.FALLBACK,
                reason="AI judge result inconsistent with deterministic findings",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        return GateResult(
            gate_type=GateType.QUALITY_CONTROL,
            decision=GateDecision.PROCEED,
            reason="Quality control checks passed",
            gate_name=self.gate_name,
        )
    
    def _has_suspicious_patterns(self, ai_result: AIJudgeResult) -> bool:
        """Check for suspicious patterns in AI result."""
        if not ai_result.worker_result:
            return True
        
        result = ai_result.worker_result
        
        # Check for generic reason codes
        generic_reasons = {"unknown", "unclear", "evaluation_failed", "error"}
        if result.reason_code.lower() in generic_reasons:
            return True
        
        # Check for missing or empty findings
        if not result.findings or len(result.findings) == 0:
            return True
        
        # Check for placeholder scores
        if result.score in (0.0, 1.0) and result.reason_code == "unknown":
            return True
        
        return False
    
    def _check_result_consistency(self, ai_result: AIJudgeResult) -> bool:
        """Check if AI result is consistent with deterministic findings."""
        # This would compare AI result with deterministic worker results
        # For now, return True as this requires additional context
        return True


class ConfidenceControlGate(DecisionGate):
    """Gate that validates AI judge confidence levels."""
    
    def _get_gate_type(self) -> GateType:
        return GateType.CONFIDENCE_CONTROL
    
    def _do_evaluate(self, context: dict[str, Any]) -> GateResult:
        """Validate confidence control conditions."""
        ai_result = context.get("ai_result")
        config = context.get("config")
        
        if not ai_result or not ai_result.success:
            return GateResult(
                gate_type=GateType.CONFIDENCE_CONTROL,
                decision=GateDecision.FALLBACK,
                reason="AI judge execution failed confidence check",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check minimum confidence
        if ai_result.confidence < config.min_confidence:
            return GateResult(
                gate_type=GateType.CONFIDENCE_CONTROL,
                decision=GateDecision.FALLBACK,
                reason=f"AI judge confidence {ai_result.confidence} below minimum {config.min_confidence}",
                gate_name=self.gate_name,
                fallback_data={"use_deterministic": True},
            )
        
        # Check for extremely high confidence (potential overconfidence)
        if ai_result.confidence > 0.99:
            logger.warning(
                f"AI judge shows extremely high confidence {ai_result.confidence}, "
                "consider reviewing calibration"
            )
        
        return GateResult(
            gate_type=GateType.CONFIDENCE_CONTROL,
            decision=GateDecision.PROCEED,
            reason="Confidence control checks passed",
            gate_name=self.gate_name,
        )


class AIJudgeGateChain:
    """
    Chain of decision gates for AI judge execution.
    
    This implements comprehensive decision gates for LLM-based workers:
    1. Pre-invocation gates: Validate before calling AI judge
    2. Post-result gates: Validate AI judge output quality
    3. Cost control gates: Prevent excessive spending
    4. Quality control gates: Ensure output quality
    5. Confidence control gates: Validate confidence levels
    """
    
    def __init__(
        self,
        pre_invocation_gate: PreInvocationGate | None = None,
        post_result_gate: PostResultGate | None = None,
        cost_control_gate: CostControlGate | None = None,
        quality_control_gate: QualityControlGate | None = None,
        confidence_control_gate: ConfidenceControlGate | None = None,
    ):
        self.pre_invocation_gate = pre_invocation_gate or PreInvocationGate("pre_invocation")
        self.post_result_gate = post_result_gate or PostResultGate("post_result")
        self.cost_control_gate = cost_control_gate or CostControlGate("cost_control")
        self.quality_control_gate = quality_control_gate or QualityControlGate("quality_control")
        self.confidence_control_gate = confidence_control_gate or ConfidenceControlGate("confidence_control")
    
    async def evaluate_pre_invocation(
        self,
        artifact,
        config: AIJudgeInvocationConfig,
        routing_criteria,
        context: dict[str, Any],
    ) -> tuple[GateDecision, GateResult]:
        """Evaluate all pre-invocation gates."""
        pre_context = {
            "artifact": artifact,
            "config": config,
            "routing_criteria": routing_criteria,
            **context,
        }
        
        result = self.pre_invocation_gate.evaluate(pre_context)
        
        logger.info(
            f"Pre-invocation gate {result.gate_name}: "
            f"{result.decision.value} - {result.reason}"
        )
        
        return result.decision, result
    
    async def evaluate_post_result(
        self,
        ai_result: AIJudgeResult,
        config: AIJudgeInvocationConfig,
        context: dict[str, Any],
    ) -> tuple[GateDecision, GateResult]:
        """Evaluate all post-result gates."""
        post_context = {
            "ai_result": ai_result,
            "config": config,
            **context,
        }
        
        # Run gates in sequence
        gates = [
            self.post_result_gate,
            self.quality_control_gate,
            self.confidence_control_gate,
        ]
        
        for gate in gates:
            result = gate.evaluate(post_context)
            
            logger.info(
                f"Post-result gate {result.gate_name}: "
                f"{result.decision.value} - {result.reason}"
            )
            
            # Block on first blocking decision
            if result.decision == GateDecision.BLOCK:
                return GateDecision.BLOCK, result
            
            # Fallback on first fallback decision
            if result.decision == GateDecision.FALLBACK:
                return GateDecision.FALLBACK, result
        
        return GateDecision.PROCEED, result
    
    def evaluate_cost_control(
        self,
        estimated_cost_usd: float,
        case_id: str,
        context: dict[str, Any],
    ) -> tuple[GateDecision, GateResult]:
        """Evaluate cost control gate."""
        cost_context = {
            "estimated_cost_usd": estimated_cost_usd,
            "case_id": case_id,
            **context,
        }
        
        result = self.cost_control_gate.evaluate(cost_context)
        
        logger.info(
            f"Cost control gate {result.gate_name}: "
            f"{result.decision.value} - {result.reason}"
        )
        
        return result.decision, result
    
    def record_actual_spending(self, case_id: str, cost_usd: float):
        """Record actual spending after successful AI judge call."""
        self.cost_control_gate.record_spending(case_id, cost_usd)
    
    def get_spending_summary(self) -> dict[str, Any]:
        """Get summary of AI judge spending."""
        return {
            "total_spent_usd": self.cost_control_gate._total_spent_usd,
            "case_spending": self.cost_control_gate._case_spending.copy(),
            "max_total_spending_usd": self.cost_control_gate.max_total_spending_usd,
            "max_per_case_spending_usd": self.cost_control_gate.max_per_case_spending_usd,
        }