"""Tests for AI judge decision gates - standalone test file."""

import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from datetime import UTC, datetime
from glyph.evaluation.specialized_workers.ai_decision_gates import (
    AIJudgeGateChain,
    AIJudgeInvocationConfig,
    AIJudgeResult,
    ConfidenceControlGate,
    CostControlGate,
    DecisionGate,
    GateDecision,
    GateResult,
    GateType,
    PostResultGate,
    PreInvocationGate,
    QualityControlGate,
)
from glyph.evaluation.specialized_workers.base import (
    WorkerResult,
    WorkerType,
    GraderMode,
    Severity,
)
from glyph.evaluation.specialized_workers.artifact import (
    ArtifactStatus,
    EvaluationArtifact,
    ExecutionMode,
    ModelManifest,
    UsageMetrics,
)
from glyph.evaluation.specialized_workers.grader_router import RoutingCriteria


def test_pre_invocation_gate_proceed():
    """Test pre-invocation gate with valid conditions."""
    print("Testing pre-invocation gate with valid conditions...")
    
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
    print("PASS: Pre-invocation gate passes with valid conditions")


def test_pre_invocation_gate_fallback_no_ai():
    """Test pre-invocation gate fallback when AI unavailable."""
    print("Testing pre-invocation gate fallback when AI unavailable...")
    
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
    print("PASS: Pre-invocation gate falls back when AI unavailable")


def test_pre_invocation_gate_block_budget():
    """Test pre-invocation gate blocks on budget exceeded."""
    print("Testing pre-invocation gate blocks on budget exceeded...")
    
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
    print("PASS: Pre-invocation gate blocks when budget exceeded")


def test_cost_control_gate_proceed():
    """Test cost control gate allows within limits."""
    print("Testing cost control gate allows within limits...")
    
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
    print("PASS: Cost control gate allows within limits")


def test_cost_control_gate_block_total():
    """Test cost control gate blocks on total budget exceeded."""
    print("Testing cost control gate blocks on total budget exceeded...")
    
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
    print("PASS: Cost control gate blocks when total budget exceeded")


def test_cost_control_gate_fallback_per_case():
    """Test cost control gate fallback on per-case limit."""
    print("Testing cost control gate fallback on per-case limit...")
    
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
    print("PASS: Cost control gate falls back when per-case limit exceeded")


def test_post_result_gate_validate_success():
    """Test post-result gate validates successful AI result."""
    print("Testing post-result gate validates successful AI result...")
    
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
    print("PASS: Post-result gate validates successful AI result")


def test_post_result_gate_fallback_low_confidence():
    """Test post-result gate fallback on low confidence."""
    print("Testing post-result gate fallback on low confidence...")
    
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
    print("PASS: Post-result gate falls back on low confidence")


def test_ai_judge_gate_chain_spending_tracking():
    """Test AI judge gate chain tracks spending."""
    print("Testing AI judge gate chain tracks spending...")
    
    gate_chain = AIJudgeGateChain()
    
    # Record some spending
    gate_chain.record_actual_spending("case_001", 0.05)
    gate_chain.record_actual_spending("case_002", 0.03)
    
    summary = gate_chain.get_spending_summary()
    
    assert summary["total_spent_usd"] == 0.08
    assert summary["case_spending"]["case_001"] == 0.05
    assert summary["case_spending"]["case_002"] == 0.03
    print("PASS: AI judge gate chain tracks spending correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing AI Decision Gates Implementation")
    print("=" * 60)
    
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
        
        print("=" * 60)
        print("All tests passed! PASS")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())