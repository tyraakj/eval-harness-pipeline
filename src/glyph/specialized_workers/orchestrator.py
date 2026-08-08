"""Evaluation orchestrator for routing evidence to specialized workers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from glyph.specialized_workers.base import (
    BaseSpecializedWorker,
    EvaluationEvidence,
    WorkerResult,
    WorkerType,
)
from glyph.specialized_workers.evaluators.graph_evaluator import GraphEvaluator
from glyph.specialized_workers.evaluators.output_evaluator import OutputEvaluator
from glyph.specialized_workers.evaluators.performance_evaluator import PerformanceEvaluator
from glyph.specialized_workers.evaluators.retrieval_evaluator import RetrievalEvaluator
from glyph.specialized_workers.evaluators.security_evaluator import SecurityEvaluator
from glyph.specialized_workers.evaluators.tool_evaluator import ToolEvaluator


@dataclass
class OrchestratorConfig:
    """Configuration for the evaluation orchestrator."""
    # Worker enablement
    enable_tool_evaluator: bool = True
    enable_retrieval_evaluator: bool = True
    enable_graph_evaluator: bool = True
    enable_output_evaluator: bool = True
    enable_security_evaluator: bool = True
    enable_performance_evaluator: bool = True
    
    # Routing strategy
    parallel_execution: bool = True
    fail_fast_on_critical: bool = True
    
    # Worker-specific configurations
    tool_evaluator_config: dict[str, Any] = field(default_factory=dict)
    retrieval_evaluator_config: dict[str, Any] = field(default_factory=dict)
    graph_evaluator_config: dict[str, Any] = field(default_factory=dict)
    output_evaluator_config: dict[str, Any] = field(default_factory=dict)
    security_evaluator_config: dict[str, Any] = field(default_factory=dict)
    performance_evaluator_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratedResult:
    """Result from orchestrated evaluation."""
    evaluation_id: str
    trial_id: str
    worker_results: dict[WorkerType, WorkerResult]
    critical_failures: list[WorkerResult]
    errors: list[dict[str, Any]]
    total_workers_ran: int
    total_workers_passed: int
    execution_order: list[WorkerType]


class EvaluationOrchestrator:
    """Orchestrates evaluation by routing evidence to specialized workers."""
    
    def __init__(self, config: OrchestratorConfig | None = None):
        self.config = config or OrchestratorConfig()
        self._workers: dict[WorkerType, BaseSpecializedWorker] = {}
        self._initialize_workers()
    
    def _initialize_workers(self) -> None:
        """Initialize specialized workers based on configuration."""
        if self.config.enable_tool_evaluator:
            self._workers[WorkerType.TOOL_POLICY] = ToolEvaluator(
                **self.config.tool_evaluator_config
            )
        
        if self.config.enable_retrieval_evaluator:
            self._workers[WorkerType.RETRIEVAL_QUALITY] = RetrievalEvaluator(
                **self.config.retrieval_evaluator_config
            )
        
        if self.config.enable_graph_evaluator:
            self._workers[WorkerType.GRAPH_COMPLIANCE] = GraphEvaluator(
                **self.config.graph_evaluator_config
            )
        
        if self.config.enable_output_evaluator:
            self._workers[WorkerType.OUTPUT_QUALITY] = OutputEvaluator(
                **self.config.output_evaluator_config
            )
        
        if self.config.enable_security_evaluator:
            self._workers[WorkerType.SECURITY] = SecurityEvaluator(
                **self.config.security_evaluator_config
            )
        
        if self.config.enable_performance_evaluator:
            self._workers[WorkerType.PERFORMANCE] = PerformanceEvaluator(
                **self.config.performance_evaluator_config
            )
    
    def orchestrate(self, evidence: EvaluationEvidence) -> OrchestratedResult:
        """Orchestrate evaluation by routing evidence to appropriate workers."""
        evaluation_id = str(uuid.uuid4())
        
        # Determine which workers should run based on evidence
        workers_to_run = self._route_evidence(evidence)
        
        # Execute workers
        if self.config.parallel_execution:
            worker_results = self._execute_parallel(workers_to_run, evidence)
        else:
            worker_results = self._execute_sequential(workers_to_run, evidence)
        
        # Identify critical failures
        critical_failures = [
            result for result in worker_results.values()
            if not result.passed and result.severity.value in ("critical", "error")
        ]
        
        # Collect errors
        errors = []
        for worker_type, result in worker_results.items():
            if not result.passed:
                errors.append({
                    "worker_type": worker_type.value,
                    "reason_code": result.reason_code,
                    "reason_message": result.reason_message,
                    "severity": result.severity.value,
                })
        
        # Calculate summary metrics
        total_workers_ran = len(worker_results)
        total_workers_passed = sum(1 for r in worker_results.values() if r.passed)
        
        # Determine execution order
        execution_order = list(worker_results.keys())
        
        return OrchestratedResult(
            evaluation_id=evaluation_id,
            trial_id=evidence.trial_id,
            worker_results=worker_results,
            critical_failures=critical_failures,
            errors=errors,
            total_workers_ran=total_workers_ran,
            total_workers_passed=total_workers_passed,
            execution_order=execution_order,
        )
    
    def _route_evidence(self, evidence: EvaluationEvidence) -> dict[WorkerType, BaseSpecializedWorker]:
        """Route evidence to workers that can evaluate it."""
        workers_to_run = {}
        
        for worker_type, worker in self._workers.items():
            if worker.can_evaluate(evidence):
                workers_to_run[worker_type] = worker
        
        return workers_to_run
    
    def _execute_parallel(
        self,
        workers_to_run: dict[WorkerType, BaseSpecializedWorker],
        evidence: EvaluationEvidence,
    ) -> dict[WorkerType, WorkerResult]:
        """Execute workers in parallel."""
        import concurrent.futures
        
        worker_results = {}
        
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # Submit all worker tasks
            future_to_worker = {
                executor.submit(worker.evaluate, evidence): worker_type
                for worker_type, worker in workers_to_run.items()
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_worker):
                worker_type = future_to_worker[future]
                try:
                    result = future.result()
                    worker_results[worker_type] = result
                    
                    # Fail fast on critical failures if configured
                    if (self.config.fail_fast_on_critical and
                        not result.passed and
                        result.severity.value in ("critical", "error")):
                        # Cancel remaining futures
                        for remaining_future in future_to_worker:
                            if not remaining_future.done():
                                remaining_future.cancel()
                        break
                except Exception as e:
                    # Create error result
                    worker_results[worker_type] = self._create_error_result(
                        worker_type, evidence, str(e)
                    )
        
        return worker_results
    
    def _execute_sequential(
        self,
        workers_to_run: dict[WorkerType, BaseSpecializedWorker],
        evidence: EvaluationEvidence,
    ) -> dict[WorkerType, WorkerResult]:
        """Execute workers sequentially."""
        worker_results = {}
        
        # Define execution order (security first, then others)
        execution_order = self._get_execution_order(workers_to_run)
        
        for worker_type in execution_order:
            if worker_type not in workers_to_run:
                continue
            
            worker = workers_to_run[worker_type]
            try:
                result = worker.evaluate(evidence)
                worker_results[worker_type] = result
                
                # Fail fast on critical failures if configured
                if (self.config.fail_fast_on_critical and
                    not result.passed and
                    result.severity.value in ("critical", "error")):
                    break
            except Exception as e:
                worker_results[worker_type] = self._create_error_result(
                    worker_type, evidence, str(e)
                )
        
        return worker_results
    
    def _get_execution_order(
        self, workers_to_run: dict[WorkerType, BaseSpecializedWorker]
    ) -> list[WorkerType]:
        """Get execution order for workers (security first)."""
        # Priority order: security > performance > tool > retrieval > graph > output
        priority_order = [
            WorkerType.SECURITY,
            WorkerType.PERFORMANCE,
            WorkerType.TOOL_POLICY,
            WorkerType.RETRIEVAL_QUALITY,
            WorkerType.GRAPH_COMPLIANCE,
            WorkerType.OUTPUT_QUALITY,
        ]
        
        ordered = []
        for worker_type in priority_order:
            if worker_type in workers_to_run:
                ordered.append(worker_type)
        
        # Add any remaining workers not in priority order
        for worker_type in workers_to_run:
            if worker_type not in ordered:
                ordered.append(worker_type)
        
        return ordered
    
    def _create_error_result(
        self,
        worker_type: WorkerType,
        evidence: EvaluationEvidence,
        error_message: str,
    ) -> WorkerResult:
        """Create an error result for a worker that failed."""
        from glyph.specialized_workers.base import (
            GraderMode,
            Severity,
        )
        
        return WorkerResult(
            evaluation_id=str(uuid.uuid4()),
            worker_type=worker_type,
            worker_version="error",
            trial_id=evidence.trial_id,
            score=0.0,
            passed=False,
            severity=Severity.ERROR,
            reason_code="worker_execution_error",
            reason_message=f"Worker execution error: {error_message}",
            evidence_refs=[],
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=0.0,
            findings={"error": error_message},
        )
    
    def register_worker(self, worker_type: WorkerType, worker: BaseSpecializedWorker) -> None:
        """Register a custom worker."""
        self._workers[worker_type] = worker
    
    def unregister_worker(self, worker_type: WorkerType) -> None:
        """Unregister a worker."""
        if worker_type in self._workers:
            del self._workers[worker_type]
    
    def get_worker(self, worker_type: WorkerType) -> BaseSpecializedWorker | None:
        """Get a registered worker by type."""
        return self._workers.get(worker_type)
    
    def list_workers(self) -> list[WorkerType]:
        """List all registered worker types."""
        return list(self._workers.keys())
