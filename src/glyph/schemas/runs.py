"""Pydantic schemas for evaluation runs API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TriggerRunRequest(BaseModel):
    """Request schema for triggering a new evaluation run."""
    config: dict[str, Any] = Field(description="Evaluation configuration")
    run_id: str | None = Field(None, description="Optional custom run ID")


class TriggerRunResponse(BaseModel):
    """Response schema for triggered evaluation run."""
    job_id: str = Field(description="Job ID for the triggered run")
    status: str = Field(description="Status of the job (e.g., 'queued')")


class RunResponse(BaseModel):
    """Response schema for evaluation run details."""
    id: str
    suite_id: str
    suite_version: str
    started_at: datetime
    finished_at: datetime
    total: int
    cases: int
    passed: int
    failed: int
    errors: int
    timeouts: int
    pass_rate: float
    average_score: float
    artifact_path: str | None
    summary: dict[str, Any] | None = None

    model_config = ConfigDict(from_attributes=True)


class RunListItem(BaseModel):
    """Simplified response schema for run list items."""
    id: str
    suite_id: str
    suite_version: str
    started_at: datetime
    finished_at: datetime
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
