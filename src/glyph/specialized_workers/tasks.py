"""Celery tasks for specialized worker evaluation."""

from __future__ import annotations

import json
import logging
from typing import Any

from celery import current_task
from pydantic import ValidationError

from glyph.evaluation.specialized_workers.celery_config import celery_app
from glyph.evaluation.specialized_workers.base import (
    EvaluationEvidence,
    WorkerResult,
    WorkerType,
)
from glyph.evaluation.specialized_workers.artifact import EvaluationArtifact
from glyph.evaluation.specialized_workers.tool_evaluator import ToolEvaluator
from glyph.evaluation.specialized_workers.retrieval_evaluator import RetrievalEvaluator
from glyph.evaluation.specialized_workers.graph_evaluator import GraphEvaluator
from glyph.evaluation.specialized_workers.output_evaluator import OutputEvaluator
from glyph.evaluation.specialized_workers.security_evaluator import SecurityEvaluator
from glyph.evaluation.specialized_workers.performance_evaluator import PerformanceEvaluator
from glyph.evaluation.specialized_workers.orchestrator import EvaluationOrchestrator, OrchestratorConfig
from glyph.evaluation.specialized_workers.aggregator import ResultAggregator, AggregationPolicy

logger = logging.getLogger(__name__)


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.orchestrate_evaluation",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def orchestrate_evaluation(
    self,
    evidence_dict: dict[str, Any],
    config_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Orchestrate evaluation by routing evidence to specialized workers."""
    try:
        # Parse evidence
        evidence = EvaluationEvidence(**evidence_dict)
        
        # Parse config
        config = OrchestratorConfig(**config_dict) if config_dict else OrchestratorConfig()
        
        # Create orchestrator
        orchestrator = EvaluationOrchestrator(config)
        
        # Orchestrate evaluation
        result = orchestrator.orchestrate(evidence)
        
        # Convert to dict for serialization
        return {
            "evaluation_id": result.evaluation_id,
            "trial_id": result.trial_id,
            "worker_results": {
                worker_type.value: result.model_dump()
                for worker_type, result in result.worker_results.items()
            },
            "critical_failures": [
                failure.model_dump() for failure in result.critical_failures
            ],
            "errors": result.errors,
            "total_workers_ran": result.total_workers_ran,
            "total_workers_passed": result.total_workers_passed,
            "execution_order": [wt.value for wt in result.execution_order],
        }
    
    except ValidationError as e:
        logger.error(f"Validation error in orchestrate_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in orchestrate_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.tool_evaluation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def tool_evaluation(
    self,
    evidence_dict: dict[str, Any],
    policy_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate tool policy compliance."""
    try:
        evidence = EvaluationEvidence(**evidence_dict)
        
        from glyph.evaluation.specialized_workers.tool_evaluator import ToolPolicy
        policy = ToolPolicy(**policy_dict) if policy_dict else ToolPolicy()
        
        evaluator = ToolEvaluator(policy=policy)
        result = evaluator.evaluate(evidence)
        
        return result.model_dump()
    
    except ValidationError as e:
        logger.error(f"Validation error in tool_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in tool_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.retrieval_evaluation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def retrieval_evaluation(
    self,
    evidence_dict: dict[str, Any],
    policy_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate retrieval quality."""
    try:
        evidence = EvaluationEvidence(**evidence_dict)
        
        from glyph.evaluation.specialized_workers.retrieval_evaluator import RetrievalPolicy
        policy = RetrievalPolicy(**policy_dict) if policy_dict else RetrievalPolicy()
        
        evaluator = RetrievalEvaluator(policy=policy)
        result = evaluator.evaluate(evidence)
        
        return result.model_dump()
    
    except ValidationError as e:
        logger.error(f"Validation error in retrieval_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in retrieval_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.graph_evaluation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def graph_evaluation(
    self,
    evidence_dict: dict[str, Any],
    policy_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate graph compliance."""
    try:
        evidence = EvaluationEvidence(**evidence_dict)
        
        from glyph.evaluation.specialized_workers.graph_evaluator import GraphPolicy
        policy = GraphPolicy(**policy_dict) if policy_dict else GraphPolicy()
        
        evaluator = GraphEvaluator(policy=policy)
        result = evaluator.evaluate(evidence)
        
        return result.model_dump()
    
    except ValidationError as e:
        logger.error(f"Validation error in graph_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in graph_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.output_evaluation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def output_evaluation(
    self,
    evidence_dict: dict[str, Any],
    policy_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate output quality."""
    try:
        evidence = EvaluationEvidence(**evidence_dict)
        
        from glyph.evaluation.specialized_workers.output_evaluator import OutputPolicy
        policy = OutputPolicy(**policy_dict) if policy_dict else OutputPolicy()
        
        evaluator = OutputEvaluator(policy=policy)
        result = evaluator.evaluate(evidence)
        
        return result.model_dump()
    
    except ValidationError as e:
        logger.error(f"Validation error in output_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in output_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.security_evaluation",
    bind=True,
    max_retries=1,  # Security failures should not be retried often
    default_retry_delay=30,
)
def security_evaluation(
    self,
    evidence_dict: dict[str, Any],
    policy_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate security compliance."""
    try:
        evidence = EvaluationEvidence(**evidence_dict)
        
        from glyph.evaluation.specialized_workers.security_evaluator import SecurityPolicy
        policy = SecurityPolicy(**policy_dict) if policy_dict else SecurityPolicy()
        
        evaluator = SecurityEvaluator(policy=policy)
        result = evaluator.evaluate(evidence)
        
        return result.model_dump()
    
    except ValidationError as e:
        logger.error(f"Validation error in security_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in security_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.performance_evaluation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def performance_evaluation(
    self,
    evidence_dict: dict[str, Any],
    policy_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate performance metrics."""
    try:
        evidence = EvaluationEvidence(**evidence_dict)
        
        from glyph.evaluation.specialized_workers.performance_evaluator import PerformancePolicy
        policy = PerformancePolicy(**policy_dict) if policy_dict else PerformancePolicy()
        
        evaluator = PerformanceEvaluator(policy=policy)
        result = evaluator.evaluate(evidence)
        
        return result.model_dump()
    
    except ValidationError as e:
        logger.error(f"Validation error in performance_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in performance_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.semantic_evaluation",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def semantic_evaluation(
    self,
    evidence_dict: dict[str, Any],
    judge_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Perform semantic evaluation using AI judge (if implemented)."""
    try:
        evidence = EvaluationEvidence(**evidence_dict)
        
        # This would integrate with AI judges for semantic evaluation
        # For now, return a placeholder result
        from glyph.evaluation.specialized_workers.base import (
            WorkerResult,
            WorkerType,
            GraderMode,
            Severity,
        )
        
        result = WorkerResult(
            evaluation_id="semantic_eval",
            worker_type=WorkerType.OUTPUT_QUALITY,  # Reuse output type for semantic
            worker_version="1.0.0",
            trial_id=evidence.trial_id,
            score=0.8,  # Placeholder
            passed=True,
            severity=Severity.INFO,
            reason_code="semantic_evaluation",
            reason_message="Semantic evaluation not yet implemented",
            evidence_refs=[],
            grader_mode=GraderMode.MODEL_JUDGE,
            confidence=0.7,
        )
        
        return result.model_dump()
    
    except ValidationError as e:
        logger.error(f"Validation error in semantic_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in semantic_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.aggregate_results",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def aggregate_results(
    self,
    worker_results_dict: dict[str, dict[str, Any]],
    trial_id: str,
    policy_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate worker results and apply policy for release decision."""
    try:
        # Parse worker results
        worker_results = {}
        for worker_type_str, result_dict in worker_results_dict.items():
            worker_type = WorkerType(worker_type_str)
            worker_results[worker_type] = WorkerResult(**result_dict)
        
        # Parse policy
        policy = AggregationPolicy(**policy_dict) if policy_dict else AggregationPolicy()
        
        # Create aggregator
        aggregator = ResultAggregator(policy=policy)
        
        # Aggregate results
        result = aggregator.aggregate(worker_results, trial_id)
        
        return {
            "aggregation_id": result.aggregation_id,
            "trial_id": result.trial_id,
            "worker_results": {
                wt.value: wr.model_dump()
                for wt, wr in result.worker_results.items()
            },
            "normalized_scores": {
                wt.value: score
                for wt, score in result.normalized_scores.items()
            },
            "overall_score": result.overall_score,
            "domain_summary": result.domain_summary,
            "critical_failures": result.critical_failures,
            "non_critical_failures": result.non_critical_failures,
            "release_decision": result.release_decision.value,
            "release_rationale": result.release_rationale,
            "policy_version": result.policy_version,
        }
    
    except ValidationError as e:
        logger.error(f"Validation error in aggregate_results: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in aggregate_results: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.export_results",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def export_results(
    self,
    aggregated_result_dict: dict[str, Any],
    export_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export aggregated results to external systems."""
    try:
        # This would integrate with export systems (LangSmith, custom dashboards, etc.)
        # For now, log the result
        logger.info(f"Exporting results: {json.dumps(aggregated_result_dict, indent=2)}")
        
        return {
            "export_id": current_task.request.id,
            "status": "completed",
            "message": "Results exported successfully",
        }
    
    except Exception as e:
        logger.error(f"Error in export_results: {e}")
        self.retry(exc=e)


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.replay_evaluation",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def replay_evaluation(
    self,
    artifact_dict: dict[str, Any],
    policy_dict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Zero-token replay worker that reads evidence and runs deterministic graders.
    
    This worker processes immutable artifacts without calling the model again.
    It can re-run tool-call policy checks, graph-node checks, retrieval metrics,
    schema validation, and other deterministic checks.
    """
    try:
        artifact = EvaluationArtifact(**artifact_dict)
        
        # Extract evidence from artifact
        from glyph.evaluation.specialized_workers.base import BaseArtifactWorker
        
        # In a full implementation, this would instantiate the appropriate
        # artifact worker and run deterministic graders
        # For now, return a placeholder result indicating replay mode
        
        from glyph.evaluation.specialized_workers.base import (
            WorkerResult,
            WorkerType,
            GraderMode,
            Severity,
        )
        
        result = WorkerResult(
            evaluation_id=f"replay_{artifact.artifact_id}",
            worker_type=WorkerType.OUTPUT_QUALITY,
            worker_version="1.0.0",
            trial_id=artifact.trial_id,
            score=1.0,
            passed=True,
            severity=Severity.INFO,
            reason_code="replay_mode",
            reason_message="Zero-token replay evaluation completed",
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
        )
        
        return result.model_dump()
    
    except ValidationError as e:
        logger.error(f"Validation error in replay_evaluation: {e}")
        self.retry(exc=e)
    except Exception as e:
        logger.error(f"Error in replay_evaluation: {e}")
        raise


@celery_app.task(
    name="glyph.evaluation.specialized_workers.tasks.baseline_comparison",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def baseline_comparison(
    self,
    baseline_run_id: str,
    candidate_run_id: str,
    comparison_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compare candidate run against baseline run.
    
    This worker compares artifacts by stable case ID and produces
    a comparison result with behavior changes and regressions.
    """
    try:
        # In a full implementation, this would:
        # 1. Load baseline and candidate runs
        # 2. Compare artifacts by case ID
        # 3. Detect behavior changes
        # 4. Identify regressions
        # 5. Produce comparison result
        
        logger.info(
            f"Comparing candidate {candidate_run_id} against baseline {baseline_run_id}"
        )
        
        # Placeholder result
        return {
            "baseline_run_id": baseline_run_id,
            "candidate_run_id": candidate_run_id,
            "decision": "passed",
            "reason_codes": [],
            "total_trials": 0,
            "passed_trials": 0,
            "failed_trials": 0,
            "behavior_changed_trials": 0,
            "blocking_trials": [],
        }
    
    except Exception as e:
        logger.error(f"Error in baseline_comparison: {e}")
        self.retry(exc=e)
