"""Storage and idempotency handling for specialized worker results."""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from glyph.specialized_workers.base import (
    WorkerResult,
    WorkerType,
)

logger = logging.getLogger(__name__)


class EvaluationAttempt(BaseModel):
    """Record of an evaluation attempt."""
    attempt_id: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    worker_type: WorkerType
    worker_version: str
    idempotency_key: str = Field(min_length=1)
    
    # Timing
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_ms: int = Field(default=0, ge=0)
    
    # Status
    status: str = Field(default="pending")  # pending, running, completed, failed, cancelled
    
    # Result (if completed)
    result: WorkerResult | None = None
    
    # Error information (if failed)
    error_type: str | None = None
    error_message: str | None = None
    
    # Retry information
    retry_count: int = Field(default=0, ge=0)
    parent_attempt_id: str | None = None


class WorkerResultStorage:
    """Storage for worker results with idempotency handling."""
    
    def __init__(self):
        # In-memory storage for demonstration
        # In production, this would use a database (PostgreSQL, Redis, etc.)
        self._attempts: dict[str, EvaluationAttempt] = {}
        self._results: dict[str, WorkerResult] = {}
        self._idempotency_index: dict[str, str] = {}  # idempotency_key -> attempt_id
    
    def generate_idempotency_key(
        self,
        trial_id: str,
        worker_type: WorkerType,
        worker_version: str,
    ) -> str:
        """Generate idempotency key for an evaluation."""
        key_string = f"{trial_id}_{worker_type}_{worker_version}"
        hash_obj = hashlib.sha256(key_string.encode())
        return hash_obj.hexdigest()
    
    def create_attempt(
        self,
        trial_id: str,
        run_id: str,
        worker_type: WorkerType,
        worker_version: str,
        retry_count: int = 0,
        parent_attempt_id: str | None = None,
    ) -> EvaluationAttempt:
        """Create a new evaluation attempt."""
        import uuid
        
        idempotency_key = self.generate_idempotency_key(
            trial_id, worker_type, worker_version
        )
        
        # Check if there's already a completed attempt with this idempotency key
        existing_attempt_id = self._idempotency_index.get(idempotency_key)
        if existing_attempt_id:
            existing_attempt = self._attempts.get(existing_attempt_id)
            if existing_attempt and existing_attempt.status == "completed":
                logger.info(
                    f"Returning existing completed attempt for idempotency key: {idempotency_key}"
                )
                return existing_attempt
        
        # Create new attempt
        attempt = EvaluationAttempt(
            attempt_id=str(uuid.uuid4()),
            trial_id=trial_id,
            run_id=run_id,
            worker_type=worker_type,
            worker_version=worker_version,
            idempotency_key=idempotency_key,
            retry_count=retry_count,
            parent_attempt_id=parent_attempt_id,
        )
        
        self._attempts[attempt.attempt_id] = attempt
        self._idempotency_index[idempotency_key] = attempt.attempt_id
        
        logger.info(
            f"Created evaluation attempt: {attempt.attempt_id} "
            f"(trial_id={trial_id}, worker_type={worker_type})"
        )
        
        return attempt
    
    def start_attempt(self, attempt_id: str) -> bool:
        """Mark an attempt as started."""
        if attempt_id not in self._attempts:
            return False
        
        attempt = self._attempts[attempt_id]
        attempt.status = "running"
        attempt.started_at = datetime.now(UTC)
        
        logger.info(f"Started evaluation attempt: {attempt_id}")
        return True
    
    def complete_attempt(
        self,
        attempt_id: str,
        result: WorkerResult,
        duration_ms: int,
    ) -> bool:
        """Mark an attempt as completed with a result."""
        if attempt_id not in self._attempts:
            return False
        
        attempt = self._attempts[attempt_id]
        attempt.status = "completed"
        attempt.completed_at = datetime.now(UTC)
        attempt.duration_ms = duration_ms
        attempt.result = result
        
        # Store result by evaluation_id for quick lookup
        self._results[result.evaluation_id] = result
        
        logger.info(
            f"Completed evaluation attempt: {attempt_id} "
            f"(evaluation_id={result.evaluation_id}, passed={result.passed})"
        )
        
        return True
    
    def fail_attempt(
        self,
        attempt_id: str,
        error_type: str,
        error_message: str,
        duration_ms: int,
    ) -> bool:
        """Mark an attempt as failed."""
        if attempt_id not in self._attempts:
            return False
        
        attempt = self._attempts[attempt_id]
        attempt.status = "failed"
        attempt.completed_at = datetime.now(UTC)
        attempt.duration_ms = duration_ms
        attempt.error_type = error_type
        attempt.error_message = error_message
        
        logger.error(
            f"Failed evaluation attempt: {attempt_id} "
            f"(error_type={error_type}, error_message={error_message})"
        )
        
        return True
    
    def cancel_attempt(self, attempt_id: str) -> bool:
        """Mark an attempt as cancelled."""
        if attempt_id not in self._attempts:
            return False
        
        attempt = self._attempts[attempt_id]
        attempt.status = "cancelled"
        attempt.completed_at = datetime.now(UTC)
        
        logger.info(f"Cancelled evaluation attempt: {attempt_id}")
        return True
    
    def get_attempt(self, attempt_id: str) -> EvaluationAttempt | None:
        """Get an attempt by ID."""
        return self._attempts.get(attempt_id)
    
    def get_attempt_by_idempotency_key(
        self, idempotency_key: str
    ) -> EvaluationAttempt | None:
        """Get an attempt by idempotency key."""
        attempt_id = self._idempotency_index.get(idempotency_key)
        if attempt_id:
            return self._attempts.get(attempt_id)
        return None
    
    def get_result(self, evaluation_id: str) -> WorkerResult | None:
        """Get a result by evaluation ID."""
        return self._results.get(evaluation_id)
    
    def get_results_for_trial(self, trial_id: str) -> list[WorkerResult]:
        """Get all results for a trial."""
        results = []
        for attempt in self._attempts.values():
            if attempt.trial_id == trial_id and attempt.result:
                results.append(attempt.result)
        return results
    
    def get_attempts_for_trial(
        self, trial_id: str, include_retries: bool = False
    ) -> list[EvaluationAttempt]:
        """Get all attempts for a trial."""
        attempts = []
        for attempt in self._attempts.values():
            if attempt.trial_id == trial_id:
                if include_retries or attempt.retry_count == 0:
                    attempts.append(attempt)
        return attempts
    
    def get_valid_result(
        self,
        trial_id: str,
        worker_type: WorkerType,
        worker_version: str,
    ) -> WorkerResult | None:
        """Get the valid terminal result according to policy."""
        idempotency_key = self.generate_idempotency_key(
            trial_id, worker_type, worker_version
        )
        
        # Get the most recent completed attempt
        attempts = [
            attempt for attempt in self._attempts.values()
            if attempt.idempotency_key == idempotency_key
            and attempt.status == "completed"
        ]
        
        if not attempts:
            return None
        
        # Sort by completion time (most recent first)
        attempts.sort(key=lambda a: a.completed_at or datetime.min, reverse=True)
        
        # Return the most recent completed result
        return attempts[0].result
    
    def cleanup_old_attempts(self, older_than_days: int = 7) -> int:
        """Clean up old attempts to prevent storage bloat."""
        cutoff = datetime.now(UTC).timestamp() - (older_than_days * 86400)
        
        to_remove = []
        for attempt_id, attempt in self._attempts.items():
            if attempt.started_at.timestamp() < cutoff:
                to_remove.append(attempt_id)
        
        for attempt_id in to_remove:
            attempt = self._attempts[attempt_id]
            del self._attempts[attempt_id]
            if attempt.idempotency_key in self._idempotency_index:
                del self._idempotency_index[attempt.idempotency_key]
        
        logger.info(f"Cleaned up {len(to_remove)} old evaluation attempts")
        return len(to_remove)
    
    def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        total_attempts = len(self._attempts)
        total_results = len(self._results)
        
        status_counts = {}
        for attempt in self._attempts.values():
            status = attempt.status
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "total_attempts": total_attempts,
            "total_results": total_results,
            "status_counts": status_counts,
            "idempotency_keys": len(self._idempotency_index),
        }


# Global storage instance
_storage_instance: WorkerResultStorage | None = None


def get_storage() -> WorkerResultStorage:
    """Get the global storage instance."""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = WorkerResultStorage()
    return _storage_instance


def reset_storage() -> None:
    """Reset the global storage instance (useful for testing)."""
    global _storage_instance
    _storage_instance = None
