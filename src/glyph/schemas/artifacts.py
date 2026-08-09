"""Pydantic schemas for artifacts API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ArtifactItem(BaseModel):
    """Schema for a single artifact item."""
    name: str = Field(description="Artifact filename")
    path: str = Field(description="Full path to the artifact file")
    size_bytes: int = Field(description="Size of the file in bytes")
    modified_at: datetime = Field(description="Last modified timestamp")

class ArtifactSummaryResponse(BaseModel):
    """Response schema for artifact summary (RunSummary)."""
    run_id: str
    suite_id: str
    suite_version: str
    total: int
    cases: int
    passed: int
    failed: int
    errors: int
    timeouts: int
    pass_rate: float
    average_score: float
    duration_ms: int
