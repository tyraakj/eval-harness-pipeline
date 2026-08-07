"""CQRS query handlers for read operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glyph.db.models import Run, Trial
from glyph.db.session import get_session


class ListRunsQuery:
    """Query to list evaluation runs with filtering and pagination."""
    
    def __init__(
        self,
        suite_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> None:
        self.suite_id = suite_id
        self.limit = limit
        self.offset = offset
    
    async def execute(self, session: AsyncSession) -> list[dict[str, Any]]:
        """Execute the query and return run records."""
        query = select(Run)
        
        if self.suite_id:
            query = query.where(Run.suite_id == self.suite_id)
        
        query = query.order_by(Run.started_at.desc())
        query = query.limit(self.limit).offset(self.offset)
        
        result = await session.execute(query)
        runs = result.scalars().all()
        
        return [
            {
                "id": run.id,
                "suite_id": run.suite_id,
                "suite_version": run.suite_version,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat(),
                "total": run.total,
                "cases": run.cases,
                "passed": run.passed,
                "failed": run.failed,
                "errors": run.errors,
                "timeouts": run.timeouts,
                "pass_rate": run.pass_rate,
                "average_score": run.average_score,
                "artifact_path": run.artifact_path,
            }
            for run in runs
        ]


class GetRunDetailQuery:
    """Query to get detailed information about a specific run."""
    
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
    
    async def execute(self, session: AsyncSession) -> dict[str, Any] | None:
        """Execute the query and return run details."""
        query = select(Run).where(Run.id == self.run_id)
        result = await session.execute(query)
        run = result.scalar_one_or_none()
        
        if run is None:
            return None
        
        return {
            "id": run.id,
            "suite_id": run.suite_id,
            "suite_version": run.suite_version,
            "started_at": run.started_at.isoformat(),
            "finished_at": run.finished_at.isoformat(),
            "total": run.total,
            "cases": run.cases,
            "passed": run.passed,
            "failed": run.failed,
            "errors": run.errors,
            "timeouts": run.timeouts,
            "pass_rate": run.pass_rate,
            "average_score": run.average_score,
            "artifact_path": run.artifact_path,
            "summary": run.summary,
        }
