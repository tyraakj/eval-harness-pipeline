"""Business logic for evaluation runs.

This service layer handles all business logic related to evaluation runs,
including CRUD operations and database interactions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from glyph.api.settings import Settings, get_settings
from glyph.db.orm_models import Run
from glyph.db.session import get_db_session
from glyph.evaluation.tasks import run_evaluation
from glyph.schemas.runs import RunListItem, RunResponse
from glyph.specialized_workers.evaluation.tasks import celery_app


class RunService:
    """Service for managing evaluation runs."""

    def __init__(
        self,
        settings: Settings = Depends(get_settings),
        session: AsyncSession = Depends(get_db_session)
    ):
        self.settings = settings
        self.session = session

    async def list_runs(
        self,
        suite_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunListItem]:
        """List evaluation runs with filtering and pagination."""
        query = select(Run)
        
        if suite_id:
            query = query.where(Run.suite_id == suite_id)
        
        query = query.order_by(Run.started_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        runs = result.scalars().all()
        
        return [
            RunListItem.model_validate(run)
            for run in runs
        ]

    async def get_run_detail(self, run_id: str) -> RunResponse | None:
        """Get detailed information about a specific run."""
        query = select(Run).where(Run.id == run_id)
        result = await self.session.execute(query)
        run = result.scalar_one_or_none()
        
        if run is None:
            return None
        
        return RunResponse.model_validate(run)

    async def trigger_run(self, config: dict[str, str], run_id: str | None = None) -> tuple[str, str]:
        """Trigger a new evaluation run."""
        generated_run_id = run_id or f"run-{uuid4()}"
        
        # Create DB record first for durability
        db_run = Run(
            id=generated_run_id,
            suite_id="pending",  # Will be updated by task
            suite_version="pending",  # Will be updated by task
            status="queued",
            started_at=datetime.now(UTC),
            finished_at=None,
            total=0,  # Will be updated by task
            cases=0,  # Will be updated by task
            passed=0,
            failed=0,
            errors=0,
            timeouts=0,
            pass_rate=0.0,
            average_score=0.0,
            artifact_path=None,
            summary={"config": config, "status": "queued"},
            task_id=None,
        )
        self.session.add(db_run)
        await self.session.commit()
        
        # Dispatch to Celery background worker
        task = run_evaluation.delay(config, generated_run_id)
        
        # Store the task_id
        await self.session.execute(
            update(Run).where(Run.id == generated_run_id).values(task_id=task.id)
        )
        await self.session.commit()
        
        return generated_run_id, "queued"

    async def cancel_run(self, run_id: str) -> bool:
        """Cancel a queued or running evaluation run."""
        query = select(Run).where(Run.id == run_id)
        result = await self.session.execute(query)
        run = result.scalar_one_or_none()
        
        if run is None or run.task_id is None or run.status in ("completed", "failed", "cancelled"):
            return False
            
        # Revoke the Celery task
        celery_app.control.revoke(run.task_id, terminate=True, signal="SIGTERM")
        
        # Update DB
        await self.session.execute(
            update(Run).where(Run.id == run_id).values(status="cancelled")
        )
        await self.session.commit()
        
        return True
