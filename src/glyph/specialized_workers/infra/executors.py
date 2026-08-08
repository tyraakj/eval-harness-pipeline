"""Live and replay executors for zero-token replay evaluation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from glyph.specialized_workers.artifact import (
    EvaluationArtifact,
    ExecutionMode,
    ModelManifest,
    UsageMetrics,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for execution."""
    case_id: str
    trial_id: str
    run_id: str
    target_version: str
    dataset_hash: str
    sandbox_hash: str
    fixture_hash: str
    
    # Execution configuration
    timeout_seconds: int = 300
    enable_sandbox: bool = True
    sandbox_config: dict[str, Any] = field(default_factory=dict)
    
    # Model configuration
    model_manifest: ModelManifest | None = None
    
    # Additional context
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """Result from execution."""
    success: bool
    artifact: EvaluationArtifact | None = None
    error: str | None = None
    execution_mode: ExecutionMode = ExecutionMode.LIVE
    duration_ms: int = 0
    
    # Token usage (for live execution)
    target_tokens_used: int = 0
    evaluator_tokens_used: int = 0
    
    # Caching information
    cache_hit: bool = False
    cache_key: str = ""


class BaseExecutor(ABC):
    """Base class for executors."""
    
    def __init__(self, mode: ExecutionMode):
        self.mode = mode
    
    @abstractmethod
    async def execute(
        self,
        context: ExecutionContext,
        case_data: dict[str, Any],
    ) -> ExecutionResult:
        """Execute the evaluation case."""
        pass
    
    @abstractmethod
    def can_execute(self, context: ExecutionContext) -> bool:
        """Check if this executor can handle the context."""
        pass


class LiveExecutor(BaseExecutor):
    """
    Live executor that actually calls the model and tools.
    
    This is used when:
    - The model or target behavior must actually be tested
    - No compatible cached artifact exists
    - Dependencies have changed requiring fresh execution
    """
    
    def __init__(self):
        super().__init__(ExecutionMode.LIVE)
    
    def can_execute(self, context: ExecutionContext) -> bool:
        """Live executor can always execute (requires model access)."""
        return context.model_manifest is not None
    
    async def execute(
        self,
        context: ExecutionContext,
        case_data: dict[str, Any],
    ) -> ExecutionResult:
        """
        Execute the case in live mode.
        
        This involves:
        1. Setting up the isolated sandbox
        2. Executing the target with real model calls
        3. Collecting tool/retrieval/graph events
        4. Creating an immutable artifact
        """
        import time
        start_time = time.time()
        
        try:
            logger.info(
                f"Starting live execution for case {context.case_id} "
                f"(trial_id={context.trial_id})"
            )
            
            # TODO: Integrate with actual target execution
            # This would call the target system (LangGraph, etc.)
            # For now, simulate execution
            events = self._simulate_execution(context, case_data)
            
            # Collect usage metrics
            usage = self._collect_usage_metrics(events)
            
            # Create immutable artifact
            artifact = EvaluationArtifact.create(
                run_id=context.run_id,
                mode=ExecutionMode.LIVE,
                case_id=context.case_id,
                trial_id=context.trial_id,
                target_version=context.target_version,
                model_manifest=context.model_manifest or ModelManifest(
                    provider="unknown",
                    model_id="unknown",
                    parameters_hash="unknown"
                ),
                dataset_hash=context.dataset_hash,
                sandbox_hash=context.sandbox_hash,
                fixture_hash=context.fixture_hash,
                events=events,
                final_output=case_data.get("expected_output", {}),
                outcome_observations=[],
                usage=usage,
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return ExecutionResult(
                success=True,
                artifact=artifact,
                execution_mode=ExecutionMode.LIVE,
                duration_ms=duration_ms,
                target_tokens_used=usage.total_tokens,
                evaluator_tokens_used=0,
                cache_hit=False,
            )
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Live execution failed: {e}")
            
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_mode=ExecutionMode.LIVE,
                duration_ms=duration_ms,
            )
    
    def _simulate_execution(
        self,
        context: ExecutionContext,
        case_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Simulate execution for demonstration.
        
        # NOT PRODUCTION READY
        """
        # In production, this would actually execute the target
        return [
            {
                "event_type": "tool_call",
                "tool_name": "python_interpreter",
                "arguments": {"code": "print('hello')"},
                "timestamp": datetime.now(UTC).isoformat(),
            },
            {
                "event_type": "retrieval",
                "query_hash": "abc123",
                "source_ids": ["doc1", "doc2"],
                "timestamp": datetime.now(UTC).isoformat(),
            },
            {
                "event_type": "graph_node",
                "node_id": "node_1",
                "node_type": "processor",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        ]
    
    def _collect_usage_metrics(self, events: list[dict[str, Any]]) -> UsageMetrics:
        """Collect usage metrics from events."""
        # In production, this would extract actual token usage
        return UsageMetrics(
            input_tokens=100,
            output_tokens=50,
            estimated_cost=0.01,
        )


class ReplayExecutor(BaseExecutor):
    """
    Replay executor that uses frozen evidence without model calls.
    
    This is used for:
    - Routine checks after evidence already exists
    - Re-running deterministic graders
    - Testing new policies without re-execution
    - Baseline comparisons
    """
    
    def __init__(self):
        super().__init__(ExecutionMode.REPLAY)
    
    def can_execute(self, context: ExecutionContext) -> bool:
        """Replay executor requires a cached artifact."""
        # In practice, this would check if an artifact is available
        return True
    
    async def execute(
        self,
        context: ExecutionContext,
        case_data: dict[str, Any],
        artifact: EvaluationArtifact,
    ) -> ExecutionResult:
        """
        Execute the case in replay mode.
        
        This involves:
        1. Loading the frozen artifact
        2. Running deterministic graders on the evidence
        3. NO model calls
        4. Zero token consumption
        """
        import time
        start_time = time.time()
        
        try:
            logger.info(
                f"Starting replay execution for case {context.case_id} "
                f"(trial_id={context.trial_id}, artifact_id={artifact.artifact_id})"
            )
            
            # Validate artifact integrity
            if not artifact.validate_integrity():
                raise ValueError("Artifact integrity check failed")
            
            # Verify artifact is replayable
            if not artifact.is_replayable():
                raise ValueError("Artifact is not replayable")
            
            # Create a replay-mode artifact (no new execution)
            replay_artifact = EvaluationArtifact.create(
                run_id=context.run_id,
                mode=ExecutionMode.REPLAY,
                case_id=context.case_id,
                trial_id=context.trial_id,
                target_version=artifact.target_version,
                model_manifest=artifact.model_manifest,
                dataset_hash=artifact.dataset_hash,
                sandbox_hash=artifact.sandbox_hash,
                fixture_hash=artifact.fixture_hash,
                events=artifact.events,  # Reuse frozen events
                final_output=artifact.final_output,
                outcome_observations=artifact.outcome_observations,
                usage=artifact.usage,  # Reuse usage (no new tokens)
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return ExecutionResult(
                success=True,
                artifact=replay_artifact,
                execution_mode=ExecutionMode.REPLAY,
                duration_ms=duration_ms,
                target_tokens_used=0,  # Zero tokens in replay mode
                evaluator_tokens_used=0,
                cache_hit=True,
                cache_key=artifact.compute_cache_key(),
            )
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Replay execution failed: {e}")
            
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_mode=ExecutionMode.REPLAY,
                duration_ms=duration_ms,
            )


class ExecutorFactory:
    """Factory for creating executors based on mode."""
    
    @staticmethod
    def create_executor(mode: ExecutionMode) -> BaseExecutor:
        """Create an executor for the given mode."""
        if mode == ExecutionMode.LIVE:
            return LiveExecutor()
        elif mode == ExecutionMode.REPLAY:
            return ReplayExecutor()
        else:
            raise ValueError(f"Unknown execution mode: {mode}")


class RunOrchestrator:
    """
    Orchestrates live and replay execution based on cache results.
    
    This is the central component that:
    1. Checks cache for compatible artifacts
    2. Routes to live or replay execution
    3. Manages the execution lifecycle
    4. Returns results with mode information
    """
    
    def __init__(self, cache_router):
        self.cache_router = cache_router
        self.executor_factory = ExecutorFactory()
    
    async def run_trial(
        self,
        context: ExecutionContext,
        case_data: dict[str, Any],
        tool_contract_hash: str = "",
        retriever_hash: str = "",
    ) -> ExecutionResult:
        """
        Run a trial with automatic live/replay routing.
        
        Args:
            context: Execution context
            case_data: Test case data
            tool_contract_hash: Hash of tool contracts (for cache key)
            retriever_hash: Hash of retriever config (for cache key)
        
        Returns:
            ExecutionResult with mode and artifact information
        """
        # Compute case hash from case data
        case_hash = self._compute_case_hash(case_data)
        
        # Get model manifest hash
        model_manifest_hash = (
            context.model_manifest.compute_hash()
            if context.model_manifest
            else ""
        )
        
        # Route execution
        mode, cached_artifact, lookup_result = self.cache_router.route_execution(
            case_hash=case_hash,
            target_version=context.target_version,
            model_manifest_hash=model_manifest_hash,
            tool_contract_hash=tool_contract_hash,
            retriever_hash=retriever_hash,
            fixture_hash=context.fixture_hash,
            sandbox_hash=context.sandbox_hash,
        )
        
        # Execute based on mode
        if mode == ExecutionMode.REPLAY and cached_artifact:
            # Replay mode: use cached artifact
            executor = self.executor_factory.create_executor(ExecutionMode.REPLAY)
            result = await executor.execute(context, case_data, cached_artifact)
            result.cache_hit = True
            result.cache_key = lookup_result.cache_key
        else:
            # Live mode: execute fresh
            executor = self.executor_factory.create_executor(ExecutionMode.LIVE)
            result = await executor.execute(context, case_data)
            result.cache_hit = False
            
            # Store result in cache if successful
            if result.success and result.artifact:
                self.cache_router.cache.store(
                    artifact=result.artifact,
                    case_hash=case_hash,
                    tool_contract_hash=tool_contract_hash,
                    retriever_hash=retriever_hash,
                )
        
        return result
    
    def _compute_case_hash(self, case_data: dict[str, Any]) -> str:
        """Compute hash of case data for cache key."""
        import hashlib
        import json
        
        case_json = json.dumps(case_data, sort_keys=True, default=str)
        return hashlib.sha256(case_json.encode()).hexdigest()