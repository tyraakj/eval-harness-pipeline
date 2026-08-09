"""Graders API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from glyph.api.rate_limit import limiter
from glyph.schemas.grader_schemas import GraderListResponse
from glyph.services.grader_service import GraderService

router = APIRouter()


@router.get("", response_model=GraderListResponse)
@limiter.limit("120/minute")
async def list_graders(
    request: Request,
    grader_service: GraderService = Depends(GraderService)
) -> GraderListResponse:
    """List available grader types."""
    return grader_service.list_graders()
