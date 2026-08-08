"""Business logic for evaluation runs.

This service layer handles all business logic related to evaluation runs,
including CRUD operations and database interactions.
"""

from __future__ import annotations

from datetime import UTC
from uuid import uuid4

from sqlalchemy import select

from glyph.db.orm_models import Run
from glyph.db.session import get_session
from glyph.evaluation.tasks import run_evaluation
from glyph.schemas.runs import RunListItem, RunResponse


class RunService:
    """Service for managing evaluation runs."""

    @staticmethod
    async def list_runs(
        suite_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RunListItem]:
        """List evaluation runs with filtering and pagination.
        
        Args:
            suite_id: Optional suite ID to filter by
            limit: Maximum number of results to return
            offset: Number of results to skip
            
        Returns:
            List of run list items
        """
        async with get_session() as session:
            query = select(Run)
            
            if suite_id:
                query = query.where(Run.suite_id == suite_id)
            
            query = query.order_by(Run.started_at.desc())
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            runs = result.scalars().all()
            
            return [
                RunListItem.model_validate(run)
                for run in runs
            ]

    @staticmethod
    async def get_run_detail(run_id: str) -> RunResponse | None:
        """Get detailed information about a specific run.
        
        Args:
            run_id: The run ID to retrieve
            
        Returns:
            Run response with details, or None if not found
        """
        async with get_session() as session:
            query = select(Run).where(Run.id == run_id)
            result = await session.execute(query)
            run = result.scalar_one_or_none()
            
            if run is None:
                return None
            
            return RunResponse.model_validate(run)

    @staticmethod
    async def trigger_run(config: dict[str, str], run_id: str | None = None) -> tuple[str, str]:
        """Trigger a new evaluation run.
        
        Args:
            config: Evaluation configuration
            run_id: Optional custom run ID
            
        Returns:
            Tuple of (job_id, status)
        """
        generated_run_id = run_id or f"run-{uuid4()}"
        
        # Create DB record first for durability
        async with get_session() as session:
            from datetime import datetime
            
            db_run = Run(
                id=generated_run_id,
                suite_id="pending",  # Will be updated by task
                suite_version="pending",  # Will be updated by task
                status="queued",
                started_at=datetime.now(UTC),
                finished_at=datetime.now(UTC),  # Temporary, will be updated
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
            session.add(db_run)
            await session.commit()
        
        # Dispatch to Celery background worker
        task = run_evaluation.delay(config, generated_run_id)
        
        # Store the task_id
        async with get_session() as session:
            from sqlalchemy import update
            await session.execute(
                update(Run).where(Run.id == generated_run_id).values(task_id=task.id)
            )
            await session.commit()
        
        return generated_run_id, "queued"

    @staticmethod
    async def cancel_run(run_id: str) -> bool:
        """Cancel a queued or running evaluation run."""
        from glyph.specialized_workers.evaluation.tasks import celery_app
        from sqlalchemy import update
        
        async with get_session() as session:
            query = select(Run).where(Run.id == run_id)
            result = await session.execute(query)
            run = result.scalar_one_or_none()
            
            if run is None or run.task_id is None or run.status in ("completed", "failed", "cancelled"):
                return False
                
            # Revoke the Celery task
            celery_app.control.revoke(run.task_id, terminate=True, signal="SIGTERM")
            
            # Update DB
            await session.execute(
                update(Run).where(Run.id == run_id).values(status="cancelled")
            )
            await session.commit()
            
            return True
