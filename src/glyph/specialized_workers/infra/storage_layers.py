"""Three-tier storage architecture for zero-token replay evaluation."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from glyph.specialized_workers.artifact import (
    EvaluationArtifact,
    ReplayBundle,
)

logger = logging.getLogger(__name__)


class StorageBackend(StrEnum):
    """Storage backend types."""
    POSTGRESQL = "postgresql"
    OBJECT_STORAGE = "object_storage"
    REDIS = "redis"


# ============================================================================
# PostgreSQL Storage - Metadata and Indexes
# ============================================================================

@dataclass
class RunMetadata:
    """Metadata stored in PostgreSQL."""
    run_id: str
    project_id: str
    user_id: str
    
    # Run configuration
    target_version: str
    dataset_version: str
    mode: str  # "live" or "replay"
    
    # Status and timing
    status: str  # "pending", "running", "completed", "failed"
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Summary statistics
    total_cases: int = 0
    completed_cases: int = 0
    failed_cases: int = 0
    
    # Token usage
    target_tokens_used: int = 0
    evaluator_tokens_used: int = 0
    
    # Cache statistics
    cache_hits: int = 0
    cache_misses: int = 0
    
    # Artifact references
    artifact_ids: list[str] = field(default_factory=list)
    
    # Release decision
    release_decision: str | None = None
    release_reason_codes: list[str] = field(default_factory=list)


class PostgreSQLStorage(ABC):
    """
    PostgreSQL storage for run metadata, users, projects, statuses, summaries, and indexes.
    
    In production, this would use SQLAlchemy or similar to interface with PostgreSQL.
    """
    
    @abstractmethod
    def store_run_metadata(self, metadata: RunMetadata) -> bool:
        """Store run metadata."""
        pass
    
    @abstractmethod
    def get_run_metadata(self, run_id: str) -> RunMetadata | None:
        """Retrieve run metadata."""
        pass
    
    @abstractmethod
    def update_run_status(self, run_id: str, status: str) -> bool:
        """Update run status."""
        pass
    
    @abstractmethod
    def list_runs_for_project(self, project_id: str) -> list[RunMetadata]:
        """List all runs for a project."""
        pass
    
    @abstractmethod
    def get_user_projects(self, user_id: str) -> list[dict[str, Any]]:
        """Get all projects for a user."""
        pass


class InMemoryPostgreSQLStorage(PostgreSQLStorage):
    """In-memory implementation of PostgreSQL storage for demonstration."""
    
    def __init__(self):
        self._runs: dict[str, RunMetadata] = {}
        self._projects: dict[str, dict[str, Any]] = {}
        self._users: dict[str, dict[str, Any]] = {}
    
    def store_run_metadata(self, metadata: RunMetadata) -> bool:
        self._runs[metadata.run_id] = metadata
        logger.info(f"Stored run metadata for {metadata.run_id}")
        return True
    
    def get_run_metadata(self, run_id: str) -> RunMetadata | None:
        return self._runs.get(run_id)
    
    def update_run_status(self, run_id: str, status: str) -> bool:
        if run_id in self._runs:
            self._runs[run_id].status = status
            if status == "running":
                self._runs[run_id].started_at = datetime.now(UTC)
            elif status in ("completed", "failed"):
                self._runs[run_id].completed_at = datetime.now(UTC)
            logger.info(f"Updated run {run_id} status to {status}")
            return True
        return False
    
    def list_runs_for_project(self, project_id: str) -> list[RunMetadata]:
        return [
            run for run in self._runs.values()
            if run.project_id == project_id
        ]
    
    def get_user_projects(self, user_id: str) -> list[dict[str, Any]]:
        return [
            project for project in self._projects.values()
            if project.get("user_id") == user_id
        ]


# ============================================================================
# Object Storage - Immutable Artifacts
# ============================================================================

class ObjectStorage(ABC):
    """
    Object storage for immutable evidence artifacts, replay bundles, and transcripts.
    
    In production, this would use S3, GCS, Azure Blob Storage, or similar.
    """
    
    @abstractmethod
    def store_artifact(self, artifact: EvaluationArtifact) -> str:
        """Store an artifact and return its storage key."""
        pass
    
    @abstractmethod
    def get_artifact(self, artifact_id: str) -> EvaluationArtifact | None:
        """Retrieve an artifact by ID."""
        pass
    
    @abstractmethod
    def store_replay_bundle(self, bundle: ReplayBundle) -> str:
        """Store a replay bundle and return its storage key."""
        pass
    
    @abstractmethod
    def get_replay_bundle(self, artifact_id: str) -> ReplayBundle | None:
        """Retrieve a replay bundle by artifact ID."""
        pass
    
    @abstractmethod
    def delete_artifact(self, artifact_id: str) -> bool:
        """Delete an artifact."""
        pass
    
    @abstractmethod
    def artifact_exists(self, artifact_id: str) -> bool:
        """Check if an artifact exists."""
        pass


class InMemoryObjectStorage(ObjectStorage):
    """In-memory implementation of object storage for demonstration."""
    
    def __init__(self):
        self._artifacts: dict[str, EvaluationArtifact] = {}
        self._replay_bundles: dict[str, ReplayBundle] = {}
    
    def store_artifact(self, artifact: EvaluationArtifact) -> str:
        storage_key = f"artifacts/{artifact.artifact_id}.json"
        self._artifacts[artifact.artifact_id] = artifact
        logger.info(f"Stored artifact {artifact.artifact_id} at {storage_key}")
        return storage_key
    
    def get_artifact(self, artifact_id: str) -> EvaluationArtifact | None:
        return self._artifacts.get(artifact_id)
    
    def store_replay_bundle(self, bundle: ReplayBundle) -> str:
        storage_key = f"bundles/{bundle.artifact.artifact_id}.json"
        self._replay_bundles[bundle.artifact.artifact_id] = bundle
        logger.info(f"Stored replay bundle for {bundle.artifact.artifact_id} at {storage_key}")
        return storage_key
    
    def get_replay_bundle(self, artifact_id: str) -> ReplayBundle | None:
        return self._replay_bundles.get(artifact_id)
    
    def delete_artifact(self, artifact_id: str) -> bool:
        if artifact_id in self._artifacts:
            del self._artifacts[artifact_id]
            if artifact_id in self._replay_bundles:
                del self._replay_bundles[artifact_id]
            logger.info(f"Deleted artifact {artifact_id}")
            return True
        return False
    
    def artifact_exists(self, artifact_id: str) -> bool:
        return artifact_id in self._artifacts


# ============================================================================
# Redis Storage - Queues, Locks, Events
# ============================================================================

@dataclass
class ProgressEvent:
    """Progress event stored in Redis."""
    run_id: str
    trial_id: str
    event_type: str  # "started", "progress", "completed", "failed"
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)


class RedisStorage(ABC):
    """
    Redis storage for queues, short-lived locks, progress events, and cancellation signals.
    
    In production, this would use Redis or similar.
    """
    
    @abstractmethod
    def enqueue_task(self, queue_name: str, task_data: dict[str, Any]) -> str:
        """Enqueue a task and return task ID."""
        pass
    
    @abstractmethod
    def dequeue_task(self, queue_name: str) -> dict[str, Any] | None:
        """Dequeue a task."""
        pass
    
    @abstractmethod
    def acquire_lock(self, lock_key: str, ttl_seconds: int = 60) -> bool:
        """Acquire a distributed lock."""
        pass
    
    @abstractmethod
    def release_lock(self, lock_key: str) -> bool:
        """Release a distributed lock."""
        pass
    
    @abstractmethod
    def publish_progress_event(self, event: ProgressEvent) -> bool:
        """Publish a progress event."""
        pass
    
    @abstractmethod
    def get_progress_events(self, run_id: str) -> list[ProgressEvent]:
        """Get progress events for a run."""
        pass
    
    @abstractmethod
    def set_cancellation_signal(self, run_id: str) -> bool:
        """Set a cancellation signal for a run."""
        pass
    
    @abstractmethod
    def check_cancellation_signal(self, run_id: str) -> bool:
        """Check if a run has been cancelled."""
        pass


class InMemoryRedisStorage(RedisStorage):
    """In-memory implementation of Redis storage for demonstration."""
    
    def __init__(self):
        self._queues: dict[str, list[dict[str, Any]]] = {}
        self._locks: dict[str, datetime] = {}
        self._progress_events: dict[str, list[ProgressEvent]] = {}
        self._cancellation_signals: set[str] = set()
    
    def enqueue_task(self, queue_name: str, task_data: dict[str, Any]) -> str:
        import uuid
        
        if queue_name not in self._queues:
            self._queues[queue_name] = []
        
        task_id = str(uuid.uuid4())
        task_data["task_id"] = task_id
        task_data["enqueued_at"] = datetime.now(UTC).isoformat()
        
        self._queues[queue_name].append(task_data)
        logger.info(f"Enqueued task {task_id} to queue {queue_name}")
        return task_id
    
    def dequeue_task(self, queue_name: str) -> dict[str, Any] | None:
        if self._queues.get(queue_name):
            task = self._queues[queue_name].pop(0)
            logger.info(f"Dequeued task {task.get('task_id')} from queue {queue_name}")
            return task
        return None
    
    def acquire_lock(self, lock_key: str, ttl_seconds: int = 60) -> bool:
        if lock_key in self._locks:
            # Check if lock has expired
            if datetime.now(UTC) < self._locks[lock_key]:
                return False  # Lock still held
        
        # Acquire lock
        from datetime import timedelta
        self._locks[lock_key] = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        logger.info(f"Acquired lock {lock_key}")
        return True
    
    def release_lock(self, lock_key: str) -> bool:
        if lock_key in self._locks:
            del self._locks[lock_key]
            logger.info(f"Released lock {lock_key}")
            return True
        return False
    
    def publish_progress_event(self, event: ProgressEvent) -> bool:
        if event.run_id not in self._progress_events:
            self._progress_events[event.run_id] = []
        
        self._progress_events[event.run_id].append(event)
        logger.info(f"Published progress event for {event.run_id}: {event.event_type}")
        return True
    
    def get_progress_events(self, run_id: str) -> list[ProgressEvent]:
        return self._progress_events.get(run_id, [])
    
    def set_cancellation_signal(self, run_id: str) -> bool:
        self._cancellation_signals.add(run_id)
        logger.info(f"Set cancellation signal for {run_id}")
        return True
    
    def check_cancellation_signal(self, run_id: str) -> bool:
        return run_id in self._cancellation_signals


# ============================================================================
# Unified Storage Manager
# ============================================================================

class StorageManager:
    """
    Unified storage manager that coordinates all three storage layers.
    
    This provides a single interface for all storage operations, routing
    to the appropriate backend based on the data type.
    """
    
    def __init__(
        self,
        postgresql_storage: PostgreSQLStorage | None = None,
        object_storage: ObjectStorage | None = None,
        redis_storage: RedisStorage | None = None,
    ):
        self.postgresql = postgresql_storage or InMemoryPostgreSQLStorage()
        self.object_storage = object_storage or InMemoryObjectStorage()
        self.redis = redis_storage or InMemoryRedisStorage()
    
    # Metadata operations (PostgreSQL)
    def store_run_metadata(self, metadata: RunMetadata) -> bool:
        return self.postgresql.store_run_metadata(metadata)
    
    def get_run_metadata(self, run_id: str) -> RunMetadata | None:
        return self.postgresql.get_run_metadata(run_id)
    
    def update_run_status(self, run_id: str, status: str) -> bool:
        return self.postgresql.update_run_status(run_id, status)
    
    # Artifact operations (Object Storage)
    def store_artifact(self, artifact: EvaluationArtifact) -> str:
        storage_key = self.object_storage.store_artifact(artifact)
        return storage_key
    
    def get_artifact(self, artifact_id: str) -> EvaluationArtifact | None:
        return self.object_storage.get_artifact(artifact_id)
    
    def store_replay_bundle(self, bundle: ReplayBundle) -> str:
        return self.object_storage.store_replay_bundle(bundle)
    
    def get_replay_bundle(self, artifact_id: str) -> ReplayBundle | None:
        return self.object_storage.get_replay_bundle(artifact_id)
    
    # Queue operations (Redis)
    def enqueue_task(self, queue_name: str, task_data: dict[str, Any]) -> str:
        return self.redis.enqueue_task(queue_name, task_data)
    
    def dequeue_task(self, queue_name: str) -> dict[str, Any] | None:
        return self.redis.dequeue_task(queue_name)
    
    # Lock operations (Redis)
    def acquire_lock(self, lock_key: str, ttl_seconds: int = 60) -> bool:
        return self.redis.acquire_lock(lock_key, ttl_seconds)
    
    def release_lock(self, lock_key: str) -> bool:
        return self.redis.release_lock(lock_key)
    
    # Progress events (Redis)
    def publish_progress(self, event: ProgressEvent) -> bool:
        return self.redis.publish_progress_event(event)
    
    def get_progress(self, run_id: str) -> list[ProgressEvent]:
        return self.redis.get_progress_events(run_id)
    
    # Cancellation (Redis)
    def cancel_run(self, run_id: str) -> bool:
        return self.redis.set_cancellation_signal(run_id)
    
    def is_cancelled(self, run_id: str) -> bool:
        return self.redis.check_cancellation_signal(run_id)