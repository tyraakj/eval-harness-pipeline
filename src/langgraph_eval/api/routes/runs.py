"""Evaluation runs API routes."""

from __future__ import annotations

from fastapi import HTTPException, Query

from langgraph_eval.schemas.runs import RunListItem, RunResponse, TriggerRunRequest, TriggerRunResponse
from langgraph_eval.services.run_service import RunService

router = APIRouter()


@router.get("", response_model=list[RunListItem])
async def list_runs(
    suite_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[RunListItem]:
    """List evaluation runs with filtering and pagination."""
    return await RunService.list_runs(suite_id=suite_id, limit=limit, offset=offset)


@router.post("", response_model=TriggerRunResponse)
async def trigger_run(request: TriggerRunRequest) -> TriggerRunResponse:
    """Trigger a new evaluation run."""
    job_id, status = await RunService.trigger_run(
        config=request.config,
        run_id=request.run_id,
    )
    return TriggerRunResponse(job_id=job_id, status=status)


@router.get("/{run_id}", response_model=RunResponse)
async def get_run_detail(run_id: str) -> RunResponse:
    """Get detailed information about a specific run."""
    run = await RunService.get_run_detail(run_id)
    
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return run
