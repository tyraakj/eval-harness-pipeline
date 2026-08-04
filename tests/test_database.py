"""Tests for database module."""

from __future__ import annotations

import pytest

try:
    from glyph.db import Run, Trial, get_session
    DATABASE_AVAILABLE = True
except ImportError:
    DATABASE_AVAILABLE = False


@pytest.mark.asyncio
async def test_database_models():
    """Test that database models can be created."""
    if not DATABASE_AVAILABLE:
        pytest.skip("Database dependencies not available. Install with: uv sync --extra web")
    
    from datetime import UTC, datetime
    
    # Create a test run
    run = Run(
        id="test-run-123",
        suite_id="test-suite",
        suite_version="1.0.0",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        total=10,
        cases=10,
        passed=8,
        failed=1,
        errors=1,
        timeouts=0,
        pass_rate=0.8,
        average_score=0.85,
        artifact_path="artifacts/test.jsonl",
        summary={"test": "data"},
    )
    
    assert run.id == "test-run-123"
    assert run.suite_id == "test-suite"
    assert run.pass_rate == 0.8
    
    # Create a test trial
    trial = Trial(
        id="trial-123",
        run_id="test-run-123",
        case_id="case-1",
        repetition_index=0,
        suite="capability",
        status="passed",
        score=1.0,
        duration_ms=500,
        started_at=datetime.now(UTC),
        record={"test": "data"},
    )
    
    assert trial.id == "trial-123"
    assert trial.run_id == "test-run-123"
    assert trial.status == "passed"


@pytest.mark.asyncio
async def test_get_session():
    """Test that database session can be created."""
    if not DATABASE_AVAILABLE:
        pytest.skip("Database dependencies not available. Install with: uv sync --extra web")
    
    async with get_session() as session:
        assert session is not None


def test_database_url_env_var():
    """Test that DATABASE_URL can be set from environment."""
    if not DATABASE_AVAILABLE:
        pytest.skip("Database dependencies not available. Install with: uv sync --extra web")
    
    from glyph.db import DATABASE_URL
    
    # Should have a default value
    assert DATABASE_URL is not None
    assert "postgresql://" in DATABASE_URL or "sqlite" in DATABASE_URL
