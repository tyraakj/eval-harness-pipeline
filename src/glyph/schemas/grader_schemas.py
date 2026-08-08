"""Pydantic schemas for graders API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GraderListResponse(BaseModel):
    """Response schema for listing available graders."""
    graders: dict[str, str] = Field(description="Dictionary of grader types and their descriptions")
