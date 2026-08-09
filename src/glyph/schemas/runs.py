"""Pydantic schemas for evaluation runs API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TriggerRunRequest(BaseModel):
    """Request schema for triggering a new evaluation run."""
    config: dict[str, Any] = Field(description="Evaluation configuration")
    run_id: str | None = Field(None, description="Optional custom run ID")
    target_factory: str | None = None


class TriggerRunResponse(BaseModel):
    """Response schema for triggered evaluation run."""
    job_id: str = Field(description="Job ID for the triggered run")
    status: str = Field(description="Status of the job (e.g., 'queued')")


class RunBase(BaseModel):
    """Base schema for run details."""
    id: str
    suite_id: str
    suite_version: str
    status: str = Field(description="Current status of the run (queued, running, completed, failed, cancelled)")
    started_at: datetime
    finished_at: datetime | None = None
    total: int
    cases: int
    passed: int
    failed: int
    errors: int
    timeouts: int
    pass_rate: float
    average_score: float
    artifact_path: str | None

    model_config = ConfigDict(from_attributes=True)


class RunResponse(RunBase):
    """Response schema for evaluation run details."""
    summary: dict[str, Any] | None = None


class RunListItem(RunBase):
    """Simplified response schema for run list items."""
    pass


class TrialListItem(BaseModel):
    """Simplified response schema for trial list items."""
    id: str
    run_id: str
    case_id: str
    suite: str
    status: str
    score: float
    duration_ms: int
    started_at: datetime
    grades: list[dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ValidateRunResponse(BaseModel):
    """Response schema for validating a run request."""
    valid: bool
    errors: list[str] = Field(default_factory=list)
