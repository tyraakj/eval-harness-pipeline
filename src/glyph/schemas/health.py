"""Pydantic schemas for health check API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response schema for health check endpoint."""
    status: str = Field(description="Health status (e.g., 'healthy')")
