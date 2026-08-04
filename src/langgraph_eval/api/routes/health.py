"""Health check API routes."""

from __future__ import annotations

from fastapi import APIRouter

from langgraph_eval.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy")
