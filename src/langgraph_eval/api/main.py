"""FastAPI application factory and configuration.

This module provides the main FastAPI application instance with proper
configuration, middleware, and route registration following FastAPI best practices.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from langgraph_eval.api.routes.datasets import router as datasets_router
from langgraph_eval.api.routes.graders import router as graders_router
from langgraph_eval.api.routes.health import router as health_router
from langgraph_eval.api.routes.runs import router as runs_router
from langgraph_eval.db.session import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle events.
    
    This function handles startup and shutdown events for the FastAPI application,
    including database connection management.
    """
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="AI Evaluation Harness API",
        description="Evaluation-as-a-Service for AI applications",
        version="1.0.0",
        lifespan=lifespan,
    )
    
    # Include routers
    app.include_router(health_router, prefix="/api", tags=["Health"])
    app.include_router(runs_router, prefix="/api/runs", tags=["Runs"])
    app.include_router(graders_router, prefix="/api/graders", tags=["Graders"])
    app.include_router(datasets_router, prefix="/api/datasets", tags=["Datasets"])
    
    return app


# Create the application instance
app = create_app()
