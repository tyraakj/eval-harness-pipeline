"""Celery configuration for specialized worker queues."""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

# Create Celery app
celery_app = Celery("glyph_evaluation")

# Queue configuration matching the architecture
QUEUE_CONFIG = {
    "eval.orchestrator": {
        "routing_key": "orchestrator",
        "priority": 10,
        "worker_concurrency": 4,
        "task_soft_time_limit": 300,  # 5 minutes
        "task_time_limit": 600,  # 10 minutes
        "description": "Run orchestrator for live/replay mode routing",
    },
    "eval.replay": {
        "routing_key": "replay",
        "priority": 9,
        "worker_concurrency": 8,  # High concurrency for zero-token replay
        "task_soft_time_limit": 60,  # 1 minute
        "task_time_limit": 120,  # 2 minutes
        "description": "Zero-token worker that reads evidence and runs deterministic graders",
    },
    "eval.deterministic": {
        "routing_key": "deterministic",
        "priority": 8,
        "worker_concurrency": 8,  # High concurrency for fast deterministic checks
        "task_soft_time_limit": 60,  # 1 minute
        "task_time_limit": 120,  # 2 minutes
        "description": "Tool, retrieval, graph, output, performance deterministic workers",
    },
    "eval.semantic": {
        "routing_key": "semantic",
        "priority": 5,
        "worker_concurrency": 2,  # Limited concurrency for AI judges
        "task_soft_time_limit": 300,  # 5 minutes
        "task_time_limit": 600,  # 10 minutes
        "description": "Optional AI-powered worker for ambiguous quality questions",
    },
    "eval.security": {
        "routing_key": "security",
        "priority": 9,  # High priority for security
        "worker_concurrency": 2,  # Isolated workers
        "task_soft_time_limit": 120,  # 2 minutes
        "task_time_limit": 300,  # 5 minutes
        "description": "Security worker for fail-closed critical violations",
    },
    "eval.comparison": {
        "routing_key": "comparison",
        "priority": 7,
        "worker_concurrency": 4,
        "task_soft_time_limit": 120,  # 2 minutes
        "task_time_limit": 300,  # 5 minutes
        "description": "Baseline comparison worker",
    },
    "eval.export": {
        "routing_key": "export",
        "priority": 1,  # Low priority
        "worker_concurrency": 2,
        "task_soft_time_limit": 600,  # 10 minutes
        "task_time_limit": 1200,  # 20 minutes
        "description": "Export worker for results and reports",
    },
}

# Default Celery configuration
celery_app.conf.update(
    # Broker settings
    broker_url="redis://localhost:6379/0",
    result_backend="redis://localhost:6379/0",
    
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Queue definitions matching the architecture
    task_queues={
        "eval.orchestrator": {
            "exchange": "evaluation",
            "routing_key": "orchestrator",
        },
        "eval.replay": {
            "exchange": "evaluation",
            "routing_key": "replay",
        },
        "eval.deterministic": {
            "exchange": "evaluation",
            "routing_key": "deterministic",
        },
        "eval.semantic": {
            "exchange": "evaluation",
            "routing_key": "semantic",
        },
        "eval.security": {
            "exchange": "evaluation",
            "routing_key": "security",
        },
        "eval.comparison": {
            "exchange": "evaluation",
            "routing_key": "comparison",
        },
        "eval.export": {
            "exchange": "evaluation",
            "routing_key": "export",
        },
    },
    
    # Default queue
    task_default_queue="eval.deterministic",
    task_default_exchange="evaluation",
    task_default_routing_key="deterministic",
    
    # Task routing matching the architecture
    task_routes={
        # Orchestrator routes to orchestrator queue
        "glyph.evaluation.specialized_workers.tasks.orchestrate_evaluation": {
            "queue": "eval.orchestrator",
            "routing_key": "orchestrator",
        },
        # Replay worker routes to replay queue
        "glyph.evaluation.specialized_workers.tasks.replay_evaluation": {
            "queue": "eval.replay",
            "routing_key": "replay",
        },
        # Tool worker routes to deterministic queue
        "glyph.evaluation.specialized_workers.tasks.tool_evaluation": {
            "queue": "eval.deterministic",
            "routing_key": "deterministic",
        },
        # Retrieval worker routes to deterministic queue
        "glyph.evaluation.specialized_workers.tasks.retrieval_evaluation": {
            "queue": "eval.deterministic",
            "routing_key": "deterministic",
        },
        # Graph worker routes to deterministic queue
        "glyph.evaluation.specialized_workers.tasks.graph_evaluation": {
            "queue": "eval.deterministic",
            "routing_key": "deterministic",
        },
        # Output worker routes to deterministic queue
        "glyph.evaluation.specialized_workers.tasks.output_evaluation": {
            "queue": "eval.deterministic",
            "routing_key": "deterministic",
        },
        # Security worker routes to security queue
        "glyph.evaluation.specialized_workers.tasks.security_evaluation": {
            "queue": "eval.security",
            "routing_key": "security",
        },
        # Performance worker routes to deterministic queue
        "glyph.evaluation.specialized_workers.tasks.performance_evaluation": {
            "queue": "eval.deterministic",
            "routing_key": "deterministic",
        },
        # Semantic worker routes to semantic queue
        "glyph.evaluation.specialized_workers.tasks.semantic_evaluation": {
            "queue": "eval.semantic",
            "routing_key": "semantic",
        },
        # Comparison worker routes to comparison queue
        "glyph.evaluation.specialized_workers.tasks.baseline_comparison": {
            "queue": "eval.comparison",
            "routing_key": "comparison",
        },
        # Export worker routes to export queue
        "glyph.evaluation.specialized_workers.tasks.export_results": {
            "queue": "eval.export",
            "routing_key": "export",
        },
    },
    
    # Worker settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    
    # Task result settings
    result_expires=3600,  # 1 hour
    result_extended=True,
    
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Rate limiting for semantic queue (AI judges)
    task_annotations={
        "glyph.evaluation.specialized_workers.tasks.semantic_evaluation": {
            "rate_limit": "10/m",  # 10 tasks per minute
        },
    },
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)


def get_queue_for_worker_type(worker_type: str) -> str:
    """Get the appropriate queue for a worker type."""
    mapping = {
        "orchestrator": "eval.orchestrator",
        "replay": "eval.replay",
        "tool_policy": "eval.deterministic",
        "retrieval_quality": "eval.deterministic",
        "graph_compliance": "eval.deterministic",
        "output_quality": "eval.deterministic",
        "security": "eval.security",
        "performance": "eval.deterministic",
        "semantic": "eval.semantic",
        "comparison": "eval.comparison",
        "export": "eval.export",
    }
    return mapping.get(worker_type, "eval.deterministic")


def get_queue_config(queue_name: str) -> dict[str, Any] | None:
    """Get configuration for a specific queue."""
    return QUEUE_CONFIG.get(queue_name)


def validate_queues() -> bool:
    """Validate that all required queues are configured."""
    required_queues = [
        "eval.orchestrator",
        "eval.replay",
        "eval.deterministic",
        "eval.semantic",
        "eval.security",
        "eval.comparison",
        "eval.export",
    ]
    
    for queue in required_queues:
        if queue not in celery_app.conf.task_queues:
            return False
    
    return True
