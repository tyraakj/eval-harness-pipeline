"""Tests for AI judge decision gates - standalone test file."""

import os
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from glyph.specialized_workers.artifact import (
    EvaluationArtifact,
    ExecutionMode,
    ModelManifest,
    UsageMetrics,
)
from glyph.specialized_workers.base import (
    GraderMode,
    Severity,
    WorkerResult,
    WorkerType,
)
from glyph.specialized_workers.gates.ai_decision_gates import (
    AIJudgeGateChain,
    AIJudgeInvocationConfig,
    AIJudgeResult,
    CostControlGate,
    GateDecision,
    GateType,
    PostResultGate,
    PreInvocationGate,
)
from glyph.specialized_workers.grader_router import RoutingCriteria


def test_pre_invocation_gate_proceed():
    """Test pre-invocation gate with valid conditions."""
    
    gate = PreInvocationGate("test_pre_invocation")
    
    model_manifest = ModelManifest(
        provider="openai",
        model_id="gpt-4",
        parameters_hash="sha256:abc123"
    )
    usage = UsageMetrics(
        input_tokens=100,
        output_tokens=50,
        estimated_cost=0.01
    )
    
    artifact = EvaluationArtifact.create(
        run_id="run_001",
        mode=ExecutionMode.LIVE,
        case_id="case_001",
        trial_id="trial_001",
        target_version="v1.0",
        model_manifest=model_manifest,
        dataset_hash="sha256:def456",
        sandbox_hash="sha256:ghi789",
        fixture_hash="sha256:jkl012",
        events=[],
        final_output={"answer": "test"},
        outcome_observations=[],
        usage=usage,
    )
    
    config = AIJudgeInvocationConfig()
    routing_criteria = RoutingCriteria(
        is_critical_case=True,
        semantic_difference_score=0.8,
    )
    
    context = {
        "ai_judge_available": True,
        "estimated_cost_usd": 0.01,
        "case_id": "case_001",
        "total_spent_usd": 0.0,
        "max_budget_usd": 1.0,
        "calls_this_minute": 0,
        "max_calls_per_minute": 10,
    }
    
    result = gate.evaluate({
        "artifact": artifact,
        "config": config,
        "routing_criteria": routing_criteria,
        **context,
    })
    
    assert result.decision == GateDecision.PROCEED
    assert result.gate_type == GateType.PRE_INVOCATION
    assert result.is_blocking is False


def test_pre_invocation_gate_fallback_no_ai():
    """Test pre-invocation gate fallback when AI unavailable."""
    
    gate = PreInvocationGate("test_pre_invocation")
    
    model_manifest = ModelManifest(
        provider="openai",
        model_id="gpt-4",
        parameters_hash="sha256:abc123"
    )
    usage = UsageMetrics(
        input_tokens=100,
        output_tokens=50,
        estimated_cost=0.01
    )
    
    artifact = EvaluationArtifact.create(
        run_id="run_001",
        mode=ExecutionMode.LIVE,
        case_id="case_001",
        trial_id="trial_001",
        target_version="v1.0",
        model_manifest=model_manifest,
        dataset_hash="sha256:def456",
        sandbox_hash="sha256:ghi789",
        fixture_hash="sha256:jkl012",
        events=[],
        final_output={"answer": "test"},
        outcome_observations=[],
        usage=usage,
    )
    
    context = {
        "ai_judge_available": False,  # AI unavailable
        "artifact": artifact,
    }
    
    result = gate.evaluate(context)
    
    assert result.decision == GateDecision.FALLBACK
    assert "use_deterministic" in result.fallback_data
    assert result.reason == "AI judge not available"


def test_pre_invocation_gate_block_budget():
    """Test pre-invocation gate blocks on budget exceeded."""
    
    gate = PreInvocationGate("test_pre_invocation")
    
    model_manifest = ModelManifest(
        provider="openai",
        model_id="gpt-4",
        parameters_hash="sha256:abc123"
    )
    usage = UsageMetrics(
        input_tokens=100,
        output_tokens=50,
        estimated_cost=0.01
    )
    
    artifact = EvaluationArtifact.create(
        run_id="run_001",
        mode=ExecutionMode.LIVE,
        case_id="case_001",
        trial_id="trial_001",
        target_version="v1.0",
        model_manifest=model_manifest,
        dataset_hash="sha256:def456",
        sandbox_hash="sha256:ghi789",
        fixture_hash="sha256:jkl012",
        events=[],
        final_output={"answer": "test"},
        outcome_observations=[],
        usage=usage,
    )
    
    context = {
        "ai_judge_available": True,
        "total_spent_usd": 0.95,
        "max_budget_usd": 1.0,
        "estimated_cost_usd": 0.1,  # Would exceed budget
        "artifact": artifact,
    }
    
    result = gate.evaluate(context)
    
    assert result.decision == GateDecision.BLOCK
    assert result.is_blocking is True
    assert "budget" in result.reason.lower()


def test_cost_control_gate_proceed():
    """Test cost control gate allows within limits."""
    
    gate = CostControlGate(
        max_total_spending_usd=10.0,
        max_per_case_spending_usd=0.5,
    )
    
    context = {
        "estimated_cost_usd": 0.01,
        "case_id": "case_001",
    }
    
    result = gate.evaluate(context)
    
    assert result.decision == GateDecision.PROCEED


def test_cost_control_gate_block_total():
    """Test cost control gate blocks on total budget exceeded."""
    
    gate = CostControlGate(max_total_spending_usd=1.0)
    
    # Record some spending
    gate.record_spending("case_001", 0.8)
    
    context = {
        "estimated_cost_usd": 0.3,  # Would exceed total
        "case_id": "case_002",
    }
    
    result = gate.evaluate(context)
    
    assert result.decision == GateDecision.BLOCK
    assert result.is_blocking is True


def test_cost_control_gate_fallback_per_case():
    """Test cost control gate fallback on per-case limit."""
    
    gate = CostControlGate(max_per_case_spending_usd=0.1)
    
    # Record spending for this case
    gate.record_spending("case_001", 0.08)
    
    context = {
        "estimated_cost_usd": 0.05,  # Would exceed per-case
        "case_id": "case_001",
    }
    
    result = gate.evaluate(context)
    
    assert result.decision == GateDecision.FALLBACK
    assert "use_deterministic" in result.fallback_data


def test_post_result_gate_validate_success():
    """Test post-result gate validates successful AI result."""
    
    gate = PostResultGate("test_post_result")
    
    # Create a proper WorkerResult
    worker_result = WorkerResult(
        evaluation_id="eval_123",
        worker_type=WorkerType.OUTPUT_QUALITY,
        worker_version="1.0.0",
        trial_id="trial_123",
        score=0.9,
        passed=True,
        severity=Severity.INFO,
        reason_code="passed",
        reason_message="Test passed",
        grader_mode=GraderMode.MODEL_JUDGE,
        confidence=0.8,
        findings={"test": "data"},
    )
    
    ai_result = AIJudgeResult(
        success=True,
        worker_result=worker_result,
        model_used="gpt-4",
        tokens_used=500,
        cost_usd=0.01,
        latency_ms=2000,
        confidence=0.8,
        output_valid=True,
        fallback_used=False,
    )
    
    config = AIJudgeInvocationConfig(min_confidence=0.7)
    
    context = {
        "ai_result": ai_result,
        "config": config,
    }
    
    result = gate.evaluate(context)
    
    assert result.decision == GateDecision.PROCEED
    assert result.gate_type == GateType.POST_RESULT


def test_post_result_gate_fallback_low_confidence():
    """Test post-result gate fallback on low confidence."""
    
    gate = PostResultGate("test_post_result")
    
    # Create a proper WorkerResult
    worker_result = WorkerResult(
        evaluation_id="eval_123",
        worker_type=WorkerType.OUTPUT_QUALITY,
        worker_version="1.0.0",
        trial_id="trial_123",
        score=0.9,
        passed=True,
        severity=Severity.INFO,
        reason_code="passed",
        reason_message="Test passed",
        grader_mode=GraderMode.MODEL_JUDGE,
        confidence=0.5,  # Below threshold
        findings={"test": "data"},
    )
    
    ai_result = AIJudgeResult(
        success=True,
        worker_result=worker_result,
        model_used="gpt-4",
        tokens_used=500,
        cost_usd=0.01,
        latency_ms=2000,
        confidence=0.5,  # Below threshold
        output_valid=True,
        fallback_used=False,
    )
    
    config = AIJudgeInvocationConfig(min_confidence=0.7)
    
    context = {
        "ai_result": ai_result,
        "config": config,
    }
    
    result = gate.evaluate(context)
    
    assert result.decision == GateDecision.FALLBACK
    assert "confidence" in result.reason.lower()


def test_ai_judge_gate_chain_spending_tracking():
    """Test AI judge gate chain tracks spending."""
    
    gate_chain = AIJudgeGateChain()
    
    # Record some spending
    gate_chain.record_actual_spending("case_001", 0.05)
    gate_chain.record_actual_spending("case_002", 0.03)
    
    summary = gate_chain.get_spending_summary()
    
    assert summary["total_spent_usd"] == 0.08
    assert summary["case_spending"]["case_001"] == 0.05
    assert summary["case_spending"]["case_002"] == 0.03


def main():
    """Run all tests."""
    
    try:
        test_pre_invocation_gate_proceed()
        test_pre_invocation_gate_fallback_no_ai()
        test_pre_invocation_gate_block_budget()
        test_cost_control_gate_proceed()
        test_cost_control_gate_block_total()
        test_cost_control_gate_fallback_per_case()
        test_post_result_gate_validate_success()
        test_post_result_gate_fallback_low_confidence()
        test_ai_judge_gate_chain_spending_tracking()
        
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())