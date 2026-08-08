"""Tests for specialized evaluation workers."""


import pytest

from glyph.specialized_workers.aggregator import (
    AggregationPolicy,
    ReleaseDecision,
    ResultAggregator,
)
from glyph.specialized_workers.base import (
    EvaluationEvidence,
    Severity,
    WorkerType,
)
from glyph.specialized_workers.evaluators.graph_evaluator import (
    GraphEvaluator,
    GraphPolicy,
)
from glyph.specialized_workers.evaluators.output_evaluator import (
    OutputEvaluator,
    OutputPolicy,
)
from glyph.specialized_workers.evaluators.performance_evaluator import (
    PerformanceEvaluator,
    PerformancePolicy,
)
from glyph.specialized_workers.evaluators.retrieval_evaluator import (
    RetrievalEvaluator,
    RetrievalPolicy,
)
from glyph.specialized_workers.evaluators.security_evaluator import (
    SecurityEvaluator,
    SecurityPolicy,
)
from glyph.specialized_workers.evaluators.tool_evaluator import (
    ToolEvaluator,
    ToolPolicy,
)
from glyph.specialized_workers.infra.storage_interface import (
    get_storage,
    reset_storage,
)
from glyph.specialized_workers.orchestrator import (
    EvaluationOrchestrator,
    OrchestratorConfig,
)


@pytest.fixture
def sample_evidence():
    """Create sample evaluation evidence."""
    return EvaluationEvidence(
        trial_id="test_trial_001",
        run_id="test_run_001",
        case_id="test_case_001",
        tool_calls=[
            {
                "tool_name": "python_interpreter",
                "arguments": {"code": "print('hello')"},
                "confirmed": True,
            }
        ],
        retrieval_events=[
            {
                "query_hash": "abc123",
                "source_ids": ["doc1", "doc2"],
                "duration_ms": 100,
            }
        ],
        graph_nodes=[
            {
                "node_id": "node_1",
                "node_type": "tool_call",
                "inputs": {"tool": "python_interpreter"},
                "outputs": {"result": "success"},
                "duration_ms": 50,
            }
        ],
        final_output={"text": "Hello world", "confidence": 0.9},
        security_events=[],
        latency_ms=500.0,
        token_usage={"input_tokens": 100, "output_tokens": 50},
        cost_usd=0.01,
    )


class TestToolEvaluator:
    """Tests for ToolEvaluator."""
    
    def test_can_evaluate_with_tool_calls(self, sample_evidence):
        """Test that evaluator can evaluate evidence with tool calls."""
        policy = ToolPolicy()
        evaluator = ToolEvaluator(policy=policy)
        assert evaluator.can_evaluate(sample_evidence) is True
    
    def test_cannot_evaluate_without_tool_calls(self):
        """Test that evaluator cannot evaluate evidence without tool calls."""
        evidence = EvaluationEvidence(
            trial_id="test_trial",
            run_id="test_run",
            case_id="test_case",
            tool_calls=[],
        )
        policy = ToolPolicy()
        evaluator = ToolEvaluator(policy=policy)
        assert evaluator.can_evaluate(evidence) is False
    
    def test_evaluates_authorized_tool(self, sample_evidence):
        """Test evaluation of authorized tool call."""
        policy = ToolPolicy(allowed_tools={"python_interpreter"})
        evaluator = ToolEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is True
        assert result.score == 1.0
        assert result.severity == Severity.INFO
    
    def test_evaluates_unauthorized_tool(self, sample_evidence):
        """Test evaluation of unauthorized tool call."""
        sample_evidence.tool_calls[0]["tool_name"] = "system_shell"
        policy = ToolPolicy(prohibited_tools={"system_shell"})
        evaluator = ToolEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert result.score == 0.0
        assert result.severity == Severity.CRITICAL
        assert "unauthorized" in result.reason_code.lower()
    
    def test_evaluates_excessive_tool_calls(self, sample_evidence):
        """Test evaluation of excessive tool calls."""
        sample_evidence.tool_calls = [
            {"tool_name": "python_interpreter", "arguments": {}, "confirmed": True}
            for _ in range(25)
        ]
        policy = ToolPolicy(max_tool_calls=20)
        evaluator = ToolEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert "excessive" in result.reason_code.lower()


class TestRetrievalEvaluator:
    """Tests for RetrievalEvaluator."""
    
    def test_can_evaluate_with_retrieval_events(self, sample_evidence):
        """Test that evaluator can evaluate evidence with retrieval events."""
        policy = RetrievalPolicy()
        evaluator = RetrievalEvaluator(policy=policy)
        assert evaluator.can_evaluate(sample_evidence) is True
    
    def test_cannot_evaluate_without_retrieval_events(self):
        """Test that evaluator cannot evaluate evidence without retrieval events."""
        evidence = EvaluationEvidence(
            trial_id="test_trial",
            run_id="test_run",
            case_id="test_case",
            retrieval_events=[],
        )
        policy = RetrievalPolicy()
        evaluator = RetrievalEvaluator(policy=policy)
        assert evaluator.can_evaluate(evidence) is False
    
    def test_evaluates_good_retrieval(self, sample_evidence):
        """Test evaluation of good retrieval quality."""
        sample_evidence.metadata["expected_relevant_sources"] = ["doc1", "doc2"]
        sample_evidence.final_output["text"] = "Hello world [1] source doc1 doc2"
        policy = RetrievalPolicy()
        evaluator = RetrievalEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is True
        assert result.score >= 0.9
    
    def test_evaluates_poor_retrieval(self, sample_evidence):
        """Test evaluation of poor retrieval quality."""
        sample_evidence.metadata["expected_relevant_sources"] = ["doc1", "doc2", "doc3"]
        sample_evidence.retrieval_events[0]["source_ids"] = ["doc4", "doc5"]
        sample_evidence.final_output["text"] = "Hello world [1] source doc4 doc5"
        policy = RetrievalPolicy(require_citations=False, require_source_grounding=False, min_relevant_sources=0)
        evaluator = RetrievalEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert result.score < 0.5


class TestGraphEvaluator:
    """Tests for GraphEvaluator."""
    
    def test_can_evaluate_with_graph_nodes(self, sample_evidence):
        """Test that evaluator can evaluate evidence with graph nodes."""
        policy = GraphPolicy()
        evaluator = GraphEvaluator(policy=policy)
        assert evaluator.can_evaluate(sample_evidence) is True
    
    def test_cannot_evaluate_without_graph_nodes(self):
        """Test that evaluator cannot evaluate evidence without graph nodes."""
        evidence = EvaluationEvidence(
            trial_id="test_trial",
            run_id="test_run",
            case_id="test_case",
            graph_nodes=[],
        )
        policy = GraphPolicy()
        evaluator = GraphEvaluator(policy=policy)
        assert evaluator.can_evaluate(evidence) is False
    
    def test_evaluates_compliant_graph(self, sample_evidence):
        """Test evaluation of compliant graph execution."""
        sample_evidence.metadata["terminal_reason"] = "success"
        policy = GraphPolicy()
        evaluator = GraphEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is True
        assert result.score == 1.0
    
    def test_evaluates_prohibited_node(self, sample_evidence):
        """Test evaluation of prohibited node visit."""
        sample_evidence.graph_nodes[0]["node_id"] = "debug_node"
        policy = GraphPolicy(prohibited_nodes={"debug_node"})
        evaluator = GraphEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert result.severity == Severity.CRITICAL


class TestOutputEvaluator:
    """Tests for OutputEvaluator."""
    
    def test_can_evaluate_with_final_output(self, sample_evidence):
        """Test that evaluator can evaluate evidence with final output."""
        policy = OutputPolicy()
        evaluator = OutputEvaluator(policy=policy)
        assert evaluator.can_evaluate(sample_evidence) is True
    
    def test_cannot_evaluate_without_final_output(self):
        """Test that evaluator cannot evaluate evidence without final output."""
        evidence = EvaluationEvidence(
            trial_id="test_trial",
            run_id="test_run",
            case_id="test_case",
            final_output={},
        )
        policy = OutputPolicy()
        evaluator = OutputEvaluator(policy=policy)
        assert evaluator.can_evaluate(evidence) is False
    
    def test_evaluates_compliant_output(self, sample_evidence):
        """Test evaluation of compliant output."""
        policy = OutputPolicy()
        evaluator = OutputEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is True
        assert result.score == 1.0
    
    def test_evaluates_missing_required_fields(self, sample_evidence):
        """Test evaluation of missing required fields."""
        sample_evidence.final_output = {"text": "Hello"}  # Missing required "confidence"
        policy = OutputPolicy(required_fields={"text", "confidence"})
        evaluator = OutputEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert "missing" in result.reason_code.lower()


class TestSecurityEvaluator:
    """Tests for SecurityEvaluator."""
    
    def test_always_can_evaluate(self, sample_evidence):
        """Test that security evaluator can always evaluate."""
        policy = SecurityPolicy()
        evaluator = SecurityEvaluator(policy=policy)
        assert evaluator.can_evaluate(sample_evidence) is True
    
    def test_evaluates_clean_execution(self, sample_evidence):
        """Test evaluation of clean execution with no security issues."""
        policy = SecurityPolicy()
        evaluator = SecurityEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is True
        assert result.score == 1.0
    
    def test_evaluates_secret_exposure(self, sample_evidence):
        """Test evaluation of secret exposure."""
        sample_evidence.final_output = {"text": "API key: sk-1234567890abcdef1234567890abcdef"}
        policy = SecurityPolicy(block_secret_exposure=True)
        evaluator = SecurityEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert result.severity == Severity.CRITICAL
        assert "secret" in result.reason_code.lower()
    
    def test_evaluates_unauthorized_tool(self, sample_evidence):
        """Test evaluation of unauthorized tool access."""
        sample_evidence.tool_calls[0]["tool_name"] = "system_shell"
        policy = SecurityPolicy(unauthorized_tool_block=True, prohibited_tools={"system_shell"})
        evaluator = SecurityEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert result.severity == Severity.CRITICAL


class TestPerformanceEvaluator:
    """Tests for PerformanceEvaluator."""
    
    def test_always_can_evaluate(self, sample_evidence):
        """Test that performance evaluator can always evaluate."""
        policy = PerformancePolicy()
        evaluator = PerformanceEvaluator(policy=policy)
        assert evaluator.can_evaluate(sample_evidence) is True
    
    def test_evaluates_good_performance(self, sample_evidence):
        """Test evaluation of good performance metrics."""
        policy = PerformancePolicy()
        evaluator = PerformanceEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is True
        assert result.score > 0.8
    
    def test_evaluates_excessive_latency(self, sample_evidence):
        """Test evaluation of excessive latency."""
        sample_evidence.latency_ms = 35000.0  # 35 seconds
        policy = PerformancePolicy(max_total_latency_ms=30000)
        evaluator = PerformanceEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert "latency" in result.reason_code.lower()
    
    def test_evaluates_excessive_cost(self, sample_evidence):
        """Test evaluation of excessive cost."""
        sample_evidence.cost_usd = 2.0
        policy = PerformancePolicy(max_cost_usd=1.0)
        evaluator = PerformanceEvaluator(policy=policy)
        result = evaluator.evaluate(sample_evidence)
        
        assert result.passed is False
        assert "cost" in result.reason_code.lower()


class TestEvaluationOrchestrator:
    """Tests for EvaluationOrchestrator."""
    
    def test_orchestrates_evaluation(self, sample_evidence):
        """Test basic orchestration of evaluation."""
        config = OrchestratorConfig()
        orchestrator = EvaluationOrchestrator(config)
        result = orchestrator.orchestrate(sample_evidence)
        
        assert result.trial_id == sample_evidence.trial_id
        assert result.total_workers_ran > 0
        assert len(result.worker_results) > 0
    
    def test_routes_to_appropriate_workers(self, sample_evidence):
        """Test that evidence is routed to appropriate workers."""
        config = OrchestratorConfig()
        orchestrator = EvaluationOrchestrator(config)
        result = orchestrator.orchestrate(sample_evidence)
        
        # Should have workers for evidence types present
        assert WorkerType.TOOL_POLICY in result.worker_results
        assert WorkerType.RETRIEVAL_QUALITY in result.worker_results
        assert WorkerType.GRAPH_COMPLIANCE in result.worker_results
        assert WorkerType.OUTPUT_QUALITY in result.worker_results
        assert WorkerType.SECURITY in result.worker_results
        assert WorkerType.PERFORMANCE in result.worker_results
    
    def test_fail_fast_on_critical(self, sample_evidence):
        """Test fail-fast behavior on critical failures."""
        sample_evidence.tool_calls[0]["tool_name"] = "system_shell"
        config = OrchestratorConfig(fail_fast_on_critical=True)
        orchestrator = EvaluationOrchestrator(config)
        result = orchestrator.orchestrate(sample_evidence)
        
        assert len(result.critical_failures) > 0


class TestResultAggregator:
    """Tests for ResultAggregator."""
    
    def test_aggregates_results(self, sample_evidence):
        """Test basic aggregation of worker results."""
        config = OrchestratorConfig()
        orchestrator = EvaluationOrchestrator(config)
        orchestrated = orchestrator.orchestrate(sample_evidence)
        
        policy = AggregationPolicy()
        aggregator = ResultAggregator(policy=policy)
        result = aggregator.aggregate(
            orchestrated.worker_results,
            sample_evidence.trial_id
        )
        
        assert result.trial_id == sample_evidence.trial_id
        assert 0.0 <= result.overall_score <= 1.0
        assert result.release_decision in [
            ReleaseDecision.PASSED,
            ReleaseDecision.BLOCKED,
            ReleaseDecision.INCONCLUSIVE,
            ReleaseDecision.NOT_COMPARABLE,
        ]
    
    def test_blocks_on_critical_security(self, sample_evidence):
        """Test blocking on critical security failures."""
        # Create a mock security failure
        from glyph.specialized_workers.base import WorkerResult
        
        worker_results = {
            WorkerType.SECURITY: WorkerResult(
                evaluation_id="sec_001",
                worker_type=WorkerType.SECURITY,
                worker_version="1.0.0",
                trial_id=sample_evidence.trial_id,
                score=0.0,
                passed=False,
                severity=Severity.CRITICAL,
                reason_code="secret_exposure",
                reason_message="Secret detected",
                evidence_refs=[],
            ),
            WorkerType.OUTPUT_QUALITY: WorkerResult(
                evaluation_id="out_001",
                worker_type=WorkerType.OUTPUT_QUALITY,
                worker_version="1.0.0",
                trial_id=sample_evidence.trial_id,
                score=0.9,
                passed=True,
                severity=Severity.INFO,
                reason_code="compliant",
                reason_message="Output compliant",
                evidence_refs=[],
            ),
        }
        
        policy = AggregationPolicy(block_on_critical_security=True)
        aggregator = ResultAggregator(policy=policy)
        result = aggregator.aggregate(worker_results, sample_evidence.trial_id)
        
        assert result.release_decision == ReleaseDecision.BLOCKED
        assert "security" in result.release_rationale.lower()
    
    def test_approves_good_results(self, sample_evidence):
        """Test approval when all workers pass with good scores."""
        # Create mock passing results
        from glyph.specialized_workers.base import WorkerResult
        
        worker_results = {
            worker_type: WorkerResult(
                evaluation_id=f"{worker_type.value}_001",
                worker_type=worker_type,
                worker_version="1.0.0",
                trial_id=sample_evidence.trial_id,
                score=0.95,
                passed=True,
                severity=Severity.INFO,
                reason_code="compliant",
                reason_message="All checks passed",
                evidence_refs=[],
            )
            for worker_type in [
                WorkerType.TOOL_POLICY,
                WorkerType.RETRIEVAL_QUALITY,
                WorkerType.GRAPH_COMPLIANCE,
                WorkerType.OUTPUT_QUALITY,
                WorkerType.SECURITY,
                WorkerType.PERFORMANCE,
            ]
        }
        
        policy = AggregationPolicy(minimum_overall_score=0.8)
        aggregator = ResultAggregator(policy=policy)
        result = aggregator.aggregate(worker_results, sample_evidence.trial_id)
        
        assert result.release_decision == ReleaseDecision.PASSED
        assert result.overall_score >= 0.8


class TestWorkerResultStorage:
    """Tests for WorkerResultStorage."""
    
    def setup_method(self):
        """Reset storage before each test."""
        reset_storage()
    
    def test_creates_attempt(self):
        """Test creation of evaluation attempt."""
        storage = get_storage()
        attempt = storage.create_attempt(
            trial_id="trial_001",
            run_id="run_001",
            worker_type=WorkerType.TOOL_POLICY,
            worker_version="1.0.0",
        )
        
        assert attempt.trial_id == "trial_001"
        assert attempt.worker_type == WorkerType.TOOL_POLICY
        assert attempt.status == "pending"
    
    def test_idempotency_key_prevents_duplicates(self):
        """Test that idempotency key prevents duplicate attempts."""
        storage = get_storage()
        
        # Create first attempt
        attempt1 = storage.create_attempt(
            trial_id="trial_001",
            run_id="run_001",
            worker_type=WorkerType.TOOL_POLICY,
            worker_version="1.0.0",
        )
        
        # Complete first attempt
        from glyph.specialized_workers.base import WorkerResult
        result = WorkerResult(
            evaluation_id="eval_001",
            worker_type=WorkerType.TOOL_POLICY,
            worker_version="1.0.0",
            trial_id="trial_001",
            score=1.0,
            passed=True,
            severity=Severity.INFO,
            reason_code="test",
            reason_message="Test",
            evidence_refs=[],
        )
        storage.complete_attempt(attempt1.attempt_id, result, 100)
        
        # Try to create duplicate attempt
        attempt2 = storage.create_attempt(
            trial_id="trial_001",
            run_id="run_002",  # Different run ID
            worker_type=WorkerType.TOOL_POLICY,
            worker_version="1.0.0",
        )
        
        # Should return the completed attempt
        assert attempt2.attempt_id == attempt1.attempt_id
        assert attempt2.status == "completed"
    
    def test_get_valid_result(self):
        """Test retrieval of valid result."""
        storage = get_storage()
        
        # Create and complete attempt
        attempt = storage.create_attempt(
            trial_id="trial_001",
            run_id="run_001",
            worker_type=WorkerType.TOOL_POLICY,
            worker_version="1.0.0",
        )
        
        from glyph.specialized_workers.base import WorkerResult
        result = WorkerResult(
            evaluation_id="eval_001",
            worker_type=WorkerType.TOOL_POLICY,
            worker_version="1.0.0",
            trial_id="trial_001",
            score=1.0,
            passed=True,
            severity=Severity.INFO,
            reason_code="test",
            reason_message="Test",
            evidence_refs=[],
        )
        storage.complete_attempt(attempt.attempt_id, result, 100)
        
        # Get valid result
        valid_result = storage.get_valid_result(
            trial_id="trial_001",
            worker_type=WorkerType.TOOL_POLICY,
            worker_version="1.0.0",
        )
        
        assert valid_result is not None
        assert valid_result.evaluation_id == "eval_001"
    
    def test_storage_stats(self):
        """Test storage statistics."""
        storage = get_storage()
        
        # Create some attempts
        for i in range(3):
            storage.create_attempt(
                trial_id=f"trial_{i}",
                run_id="run_001",
                worker_type=WorkerType.TOOL_POLICY,
                worker_version="1.0.0",
            )
        
        stats = storage.get_storage_stats()
        assert stats["total_attempts"] == 3
        assert stats["status_counts"]["pending"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
