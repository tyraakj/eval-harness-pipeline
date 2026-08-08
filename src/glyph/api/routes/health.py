"""Health check API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from glyph.schemas.health import HealthResponse
from glyph.db.session import get_db_session
from glyph.api.rate_limit import limiter
from glyph.api.settings import Settings, get_settings

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
@limiter.exempt
async def health_check(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> HealthResponse:
    """Health check endpoint."""
    db_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
        
    broker_status = "unconfigured"
    if settings.celery_broker_url:
        broker_status = "ok"  # Simplified broker check for now
        
    status = "healthy"
    if db_status == "error":
        status = "unhealthy"
    elif broker_status == "error":
        status = "degraded"
        
    response = HealthResponse(
        status=status,
        db=db_status,
        broker=broker_status
    )
    
    if status == "unhealthy":
        raise HTTPException(status_code=503, detail=response.model_dump())
        
    return response
