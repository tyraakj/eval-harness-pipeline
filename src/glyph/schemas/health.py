"""Pydantic schemas for health check API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response schema for health check endpoint."""
    status: str = Field(description="Health status ('healthy', 'degraded', 'unhealthy')")
    db: str = Field(description="Database status ('ok', 'error')")
    broker: str = Field(description="Broker status ('ok', 'unconfigured', 'error')")
