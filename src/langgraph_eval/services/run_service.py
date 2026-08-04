"""Business logic for evaluation runs.

This service layer handles all business logic related to evaluation runs,
including CRUD operations and database interactions.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from langgraph_eval.db.models import Run
from langgraph_eval.db.session import get_session
from langgraph_eval.evaluation.tasks import run_evaluation
from langgraph_eval.schemas.runs import RunListItem, RunResponse


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
        
        # Dispatch to Celery background worker
        task = run_evaluation.delay(config, generated_run_id)
        
        return generated_run_id, "queued"
