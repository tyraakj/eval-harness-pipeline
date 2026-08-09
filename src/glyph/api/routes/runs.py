"""Evaluation runs API routes."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from glyph.api.rate_limit import limiter
from glyph.db.orm_models import Run, Trial
from glyph.db.session import get_db_session
from glyph.schemas.runs import (
    RunListItem,
    RunResponse,
    TrialListItem,
    TriggerRunRequest,
    TriggerRunResponse,
    ValidateRunResponse,
)
from glyph.services.run_service import RunService

router = APIRouter()

@router.get("", response_model=list[RunListItem])
@limiter.limit("120/minute")
async def list_runs(
    request: Request,
    suite_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    run_service: RunService = Depends(RunService),
) -> list[RunListItem]:
    """List evaluation runs with filtering and pagination."""
    return await run_service.list_runs(suite_id=suite_id, limit=limit, offset=offset)


@router.post("", response_model=TriggerRunResponse)
@limiter.limit("10/minute")
async def trigger_run(
    request: Request,
    run_request: TriggerRunRequest,
    run_service: RunService = Depends(RunService),
) -> TriggerRunResponse:
    """Trigger a new evaluation run."""
    job_id, status = await run_service.trigger_run(
        config=run_request.config,
        run_id=run_request.run_id,
    )
    return TriggerRunResponse(job_id=job_id, status=status)


@router.get("/{run_id}", response_model=RunResponse)
@limiter.limit("120/minute")
async def get_run_detail(
    request: Request,
    run_id: str,
    run_service: RunService = Depends(RunService),
) -> RunResponse:
    """Get detailed information about a specific run."""
    run = await run_service.get_run_detail(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/trials", response_model=list[TrialListItem])
@limiter.limit("120/minute")
async def get_run_trials(
    request: Request,
    run_id: str,
    status: str | None = Query(None),
    suite: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db_session),
) -> list[TrialListItem]:
    """Get trials for a run."""
    query = select(Trial).where(Trial.run_id == run_id)
    if status:
        query = query.where(Trial.status == status)
    if suite:
        query = query.where(Trial.suite == suite)
    
    query = query.order_by(Trial.started_at.asc())
    query = query.limit(limit).offset(offset)
    
    result = await session.execute(query)
    trials = result.scalars().all()
    
    return [TrialListItem.model_validate(t) for t in trials]


@router.get("/{run_id}/stream")
@limiter.limit("20/minute")
async def stream_run(
    request: Request,
    run_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """Stream run progress using SSE."""
    async def event_generator():
        last_trial_count = 0
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            result = await session.execute(select(Run).where(Run.id == run_id))
            run = result.scalar_one_or_none()
            
            if run is None:
                yield f"data: {json.dumps({'error': 'Run not found'})}\n\n"
                break
                
            # Yield any new trial events
            # For simplicity, we just look at the passed/failed/errors count, but in a real
            # scenario you'd track exactly which trials were completed.
            current_trials = run.passed + run.failed + run.errors
            if current_trials > last_trial_count:
                yield f"data: {json.dumps({'event': 'progress', 'completed': current_trials, 'total': run.cases})}\n\n"
                last_trial_count = current_trials

            if run.status in ("completed", "failed", "cancelled"):
                yield f"data: {json.dumps({'event': 'run_complete', 'run_id': run.id, 'status': run.status, 'pass_rate': run.pass_rate})}\n\n"
                break
                
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.delete("/{run_id}")
@limiter.limit("120/minute")
async def cancel_run(
    request: Request,
    run_id: str,
    run_service: RunService = Depends(RunService),
):
    """Cancel a run."""
    success = await run_service.cancel_run(run_id)
    if not success:
        raise HTTPException(status_code=409, detail="Run could not be cancelled or is already terminal.")
    return {"cancelled": True}


@router.post("/{run_id}/rerun", response_model=TriggerRunResponse)
@limiter.limit("120/minute")
async def rerun_run(
    request: Request,
    run_id: str,
    run_service: RunService = Depends(RunService),
) -> TriggerRunResponse:
    """Rerun an existing run using its original config."""
    run = await run_service.get_run_detail(run_id)
    if not run or not run.summary or "config" not in run.summary:
        raise HTTPException(status_code=404, detail="Run config not found")
        
    job_id, status = await run_service.trigger_run(config=run.summary["config"])
    return TriggerRunResponse(job_id=job_id, status=status)


@router.post("/validate", response_model=ValidateRunResponse)
@limiter.limit("120/minute")
async def validate_run(
    request: Request,
    run_request: TriggerRunRequest,
    run_service: RunService = Depends(RunService),
) -> ValidateRunResponse:
    """Validate a run configuration without starting it."""
    config = run_request.config
    errors = []
    
    if "factory" not in config:
        errors.append("Missing 'factory' in config")
    if "dataset" not in config:
        errors.append("Missing 'dataset' in config")
    else:
        dataset_path = Path(run_service.settings.datasets_dir) / config["dataset"]
        # Allow passing the .jsonl extension or not
        if not dataset_path.exists() and dataset_path.with_suffix('.jsonl').exists():
            dataset_path = dataset_path.with_suffix('.jsonl')
            
        if not dataset_path.exists():
            errors.append(f"Dataset file '{config['dataset']}' not found in {run_service.settings.datasets_dir}")
        else:
            try:
                with open(dataset_path, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            json.loads(line)
                            break
            except Exception:
                errors.append("Dataset file is not valid JSONL")
                
    return ValidateRunResponse(valid=len(errors) == 0, errors=errors)
