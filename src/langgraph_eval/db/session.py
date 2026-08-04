"""Database connection management.

This module provides async database session management using SQLAlchemy
with asyncpg driver, optimized for Neon serverless PostgreSQL.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from langgraph_eval.db.models import Base

# Database URL from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://ai_eval:localdev@localhost:5432/ai_eval",
)

_engine = None
_async_session_maker = None


def get_engine():
    """Get or create the async database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_maker():
    """Get or create the async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_maker


async def get_session() -> AsyncSession:
    """Get a new async database session."""
    session_maker = get_session_maker()
    return session_maker()


async def init_db() -> None:
    """Initialize database schema."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    global _engine, _async_session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None
