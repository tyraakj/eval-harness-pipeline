"""FastAPI application factory and configuration.

This module provides the main FastAPI application instance with proper
configuration, middleware, and route registration following FastAPI best practices.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from glyph.api.rate_limit import limiter
from glyph.api.routes.artifacts import router as artifacts_router
from glyph.api.routes.compare import router as compare_router
from glyph.api.routes.datasets import router as datasets_router
from glyph.api.routes.graders import router as graders_router
from glyph.api.routes.guide import router as guide_router
from glyph.api.routes.health import router as health_router
from glyph.api.routes.runs import router as runs_router
from glyph.db.session import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle events."""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Glyphuation Harness API",
        description="Evaluation-as-a-Service for AI applications",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # Configure SlowAPI
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    
    # Include routers
    app.include_router(health_router, prefix="/api", tags=["Health"])
    app.include_router(runs_router, prefix="/api/runs", tags=["Runs"])
    app.include_router(graders_router, prefix="/api/graders", tags=["Graders"])
    app.include_router(datasets_router, prefix="/api/datasets", tags=["Datasets"])
    app.include_router(compare_router, prefix="/api", tags=["Compare & Release"])
    app.include_router(artifacts_router, prefix="/api/artifacts", tags=["Artifacts"])
    app.include_router(guide_router, prefix="/api/guide", tags=["Guide"])
    
    return app


# Create the application instance
app = create_app()
