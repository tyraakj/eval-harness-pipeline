"""Celery tasks for background evaluation runs."""

from __future__ import annotations

import asyncio
from typing import Any

from celery import Celery
from sqlalchemy import update

from glyph.cli.cli import _load_factory
from glyph.core.models import RunSummary
from glyph.db.models import Run
from glyph.db.session import get_session
from glyph.evaluation.definition import EvaluationDefinition
from glyph.evaluation.runner import EvaluationRunner
from glyph.utils.datasets import load_jsonl

celery_app = Celery(
    "ai_eval",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)


async def _execute_and_save_run(config: dict[str, Any], run_id: str) -> dict[str, Any]:
    """Async helper to execute the evaluation runner and save to DB."""
    factory_ref = config.get("factory")
    dataset_path = config.get("dataset")
    output_path = config.get("output", f"artifacts/{run_id}.jsonl")
    
    if not factory_ref or not dataset_path:
        raise ValueError("config must include 'factory' and 'dataset'")
    
    # Update status to running
    async with get_session() as session:
        await session.execute(
            update(Run).where(Run.id == run_id).values(status="running")
        )
        await session.commit()
        
    # Load definition
    definition = _load_factory(factory_ref)()
    if not isinstance(definition, EvaluationDefinition):
        raise ValueError("Factory must return EvaluationDefinition")
        
    cases = load_jsonl(dataset_path)
    
    runner = EvaluationRunner(
        target=definition.target,
        graders=definition.graders,
        budget=definition.budget,
        artifact_path=output_path,
        suite=definition.suite,
        outcome_collectors=definition.outcome_collectors,
        grader_policy=definition.grader_policy,
        repetitions=definition.repetitions,
        telemetry=definition.telemetry,
        sandbox_provider=definition.sandbox_provider,
        sandbox_requirements=definition.sandbox_requirements,
        exporters=definition.exporters,
        export_policy=definition.export_policy,
        prompt_hashes=definition.prompt_hashes,
        overwrite_artifact=True,
    )
    
    # Run evaluation
    summary: RunSummary = await runner.run(cases, run_id=run_id)
    
    # Update database with results
    async with get_session() as session:
        await session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                suite_id=summary.evaluation_suite_id,
                suite_version=summary.evaluation_suite_version,
                status="completed",
                started_at=summary.started_at,
                finished_at=summary.finished_at,
                total=summary.total,
                cases=summary.cases,
                passed=summary.passed,
                failed=summary.failed,
                errors=summary.errors,
                timeouts=summary.timeouts,
                pass_rate=summary.pass_rate,
                average_score=summary.average_score,
                artifact_path=str(summary.artifact_path),
                summary=summary.model_dump(mode="json"),
            )
        )
        await session.commit()
        
    return summary.model_dump(mode="json")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_evaluation(self, config: dict, run_id: str) -> dict:
    """Execute evaluation run as a background task."""
    self.update_state(state="PROGRESS", meta={"run_id": run_id, "status": "running"})
    
    try:
        # Execute the async runner in a new event loop
        result_dict = asyncio.run(_execute_and_save_run(config, run_id))
        
        return {"run_id": run_id, "status": "completed", "summary": result_dict}
    except Exception as exc:
        # Update DB status to failed
        asyncio.run(_update_run_status_failed(run_id, str(exc)))
        
        # Retry for transient errors
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc)
        
        # For non-retryable errors or max retries exceeded
        return {"run_id": run_id, "status": "failed", "error": str(exc)}


async def _update_run_status_failed(run_id: str, error_message: str) -> None:
    """Update run status to failed in database."""
    async with get_session() as session:
        from sqlalchemy import update
        from datetime import datetime, timezone
        
        await session.execute(
            update(Run)
            .where(Run.id == run_id)
            .values(
                status="failed",
                finished_at=datetime.now(timezone.utc),
                summary={"error": error_message, "status": "failed"},
            )
        )
        await session.commit()
