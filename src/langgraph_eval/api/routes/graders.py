"""Graders API routes."""

from __future__ import annotations

from fastapi import APIRouter

from langgraph_eval.schemas.graders import GraderListResponse
from langgraph_eval.services.grader_service import GraderService

router = APIRouter()


@router.get("", response_model=GraderListResponse)
async def list_graders() -> GraderListResponse:
    """List available grader types."""
    return GraderService.list_graders()
