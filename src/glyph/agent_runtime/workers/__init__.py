"""Specialized workers for domain-specific evaluations.

This module provides a worker system for evaluating different aspects of AI agent
executions with domain-specific expertise. Workers can analyze tool calls, metadata,
intermediate steps, and LangGraph node/edge executions.

Example:
    from glyph.agent_runtime import WorkerCoordinator, WorkerRegistry
    
    # Create registry and register default workers
    registry = WorkerRegistry()
    expertises = registry.create_default_workers()
    
    # Create coordinator and register workers
    coordinator = WorkerCoordinator()
    for expertise in expertises:
        coordinator.register_worker(expertise)
    
    # Submit a task for domain-specific evaluation
    task = WorkerTask(
        task_id="eval-001",
        domain=WorkerDomain.CODE_EXECUTION,
        required_capabilities=frozenset([WorkerCapability.CODE_GENERATION]),
        target_tools=frozenset(["python_interpreter"]),
    )
    result = await coordinator.submit_task(task)
"""

from glyph.agent_runtime.coordinator import WorkerCoordinator
from glyph.agent_runtime.langgraph_integration import (
    LangGraphExecution,
    LangGraphTracer,
    LangGraphWorkerAdapter,
)
from glyph.agent_runtime.worker_models import (
    NodeAnalysisCriteria,
    ToolExpertise,
    WorkerCapability,
    WorkerDomain,
    WorkerExpertise,
    WorkerResult,
    WorkerRouting,
    WorkerTask,
)
from glyph.agent_runtime.registry import WorkerDefinition, WorkerRegistry

__all__ = [
    # Core models
    "WorkerDomain",
    "WorkerCapability",
    "WorkerExpertise",
    "WorkerTask",
    "WorkerResult",
    "WorkerRouting",
    "ToolExpertise",
    "NodeAnalysisCriteria",
    # Coordinator
    "WorkerCoordinator",
    # Registry
    "WorkerRegistry",
    "WorkerDefinition",
    # LangGraph integration
    "LangGraphTracer",
    "LangGraphExecution",
    "LangGraphWorkerAdapter",
]
