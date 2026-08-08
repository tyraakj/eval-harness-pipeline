"""Pydantic schemas for comparison and release API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ComparisonRequest(BaseModel):
    """Request schema for comparing two runs."""
    candidate_path: str = Field(description="Path to the candidate artifact JSONL")
    baseline_path: str = Field(description="Path to the baseline artifact JSONL")


class ComparisonResponse(BaseModel):
    """Response schema for run comparison."""
    common_cases: int
    improved: list[dict[str, Any]]
    regressed: list[dict[str, Any]]
    unchanged: list[dict[str, Any]]
    candidate_pass_rate: float
    baseline_pass_rate: float
    pass_rate_delta: float


class ReleaseRequest(BaseModel):
    """Request schema for evaluating a release."""
    artifact_path: str = Field(description="Path to the candidate artifact JSONL")
    policy: str = Field(description="Release policy preset name (default, staging, strict, development)")
    baseline_path: str | None = Field(None, description="Optional path to a baseline artifact JSONL")


class ReleaseDecisionResponse(BaseModel):
    """Response schema for a release decision."""
    allowed: bool
    policy_name: str
    reasons: list[str] = Field(default_factory=list)
    candidate_pass_rate: float
    baseline_pass_rate: float | None = None
