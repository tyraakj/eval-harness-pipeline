"""Compare and release API routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from glyph.api.rate_limit import limiter
from glyph.grading.comparison import compare
from glyph.schemas.compare import (
    ComparisonRequest,
    ComparisonResponse,
    ReleaseDecisionResponse,
    ReleaseRequest,
)
from glyph.specialized_workers.gates.release_gate import ReleaseGate

router = APIRouter()

def _load_run_summary(path: str):
    """Load RunSummary from artifact path JSONL (last line)."""
    import os

    from glyph.core.domain_models import RunSummary
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Artifact not found at {path}")
        
    try:
        with open(path, encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            
        if not lines:
            raise HTTPException(status_code=422, detail="Artifact file is empty")
            
        # Run summary should be the last line
        summary_line = lines[-1]
        data = json.loads(summary_line)
        if data.get("event") != "run_complete":
            # Might not be completed properly
            raise ValueError("No run_complete event found")
            
        return RunSummary(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to load run summary: {e!s}")

@router.post("/compare", response_model=ComparisonResponse)
@limiter.limit("30/minute")
async def compare_runs(
    request: Request,
    comp_request: ComparisonRequest,
) -> ComparisonResponse:
    """Compare a candidate run against a baseline."""
    try:
        from glyph.grading.comparison import Comparison
        result: Comparison = compare(Path(comp_request.candidate_path), Path(comp_request.baseline_path))
        
        return ComparisonResponse(
            common_cases=result.common_cases,
            improved=[c.model_dump() for c in result.improved],
            regressed=[c.model_dump() for c in result.regressed],
            unchanged=[c.model_dump() for c in result.unchanged],
            candidate_pass_rate=result.candidate_pass_rate,
            baseline_pass_rate=result.baseline_pass_rate,
            pass_rate_delta=result.pass_rate_delta,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

@router.post("/release", response_model=ReleaseDecisionResponse)
@limiter.limit("30/minute")
async def evaluate_release(
    request: Request,
    release_request: ReleaseRequest,
) -> ReleaseDecisionResponse:
    """Evaluate if a run is safe to release."""
    summary = _load_run_summary(release_request.artifact_path)
    gate = ReleaseGate(preset=release_request.policy)
    
    try:
        decision = gate.evaluate_release(summary, comparison_baseline=release_request.baseline_path)
        return ReleaseDecisionResponse(
            allowed=decision.allowed,
            policy_name=decision.policy_name,
            reasons=decision.reasons,
            candidate_pass_rate=decision.candidate_pass_rate,
            baseline_pass_rate=decision.baseline_pass_rate,
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

from pydantic import BaseModel

class CompareTargetsRequest(BaseModel):
    factory: str
    target_a: str
    target_b: str
    dataset: str
    config: dict | None = None

class CompareTargetsJobResponse(BaseModel):
    job_id: str
    run_id_a: str
    run_id_b: str

class CompareTargetsStatusResponse(BaseModel):
    status: str
    run_id_a: str
    run_id_b: str
    comparison: dict | None = None

_COMPARE_JOBS: dict[str, dict] = {}

from fastapi import Depends
from glyph.services.run_service import RunService

@router.post("/compare-targets", response_model=CompareTargetsJobResponse)
@limiter.limit("30/minute")
async def start_compare_targets(
    request: Request,
    comp_request: CompareTargetsRequest,
    run_service: RunService = Depends(RunService),
):
    """Trigger a side-by-side run of two targets."""
    import uuid
    job_id = str(uuid.uuid4())
    
    base_config = comp_request.config or {}
    base_config["factory"] = comp_request.factory
    base_config["dataset"] = comp_request.dataset
    
    config_a = base_config.copy()
    config_a["target_factory"] = comp_request.target_a
    config_a["output"] = f"artifacts/compare-{job_id}-a.jsonl"
    
    config_b = base_config.copy()
    config_b["target_factory"] = comp_request.target_b
    config_b["output"] = f"artifacts/compare-{job_id}-b.jsonl"
    
    job_a, status_a = await run_service.trigger_run(config_a)
    job_b, status_b = await run_service.trigger_run(config_b)
    
    _COMPARE_JOBS[job_id] = {
        "run_id_a": job_a,
        "run_id_b": job_b,
        "status": "running"
    }
    
    return CompareTargetsJobResponse(job_id=job_id, run_id_a=job_a, run_id_b=job_b)

@router.get("/compare-targets/{job_id}", response_model=CompareTargetsStatusResponse)
@limiter.limit("60/minute")
async def get_compare_targets_status(
    request: Request,
    job_id: str,
    run_service: RunService = Depends(RunService),
):
    """Check status of a compare targets job."""
    if job_id not in _COMPARE_JOBS:
        raise HTTPException(status_code=404, detail="Job not found")
        
    job = _COMPARE_JOBS[job_id]
    
    run_a = await run_service.get_run_detail(job["run_id_a"])
    run_b = await run_service.get_run_detail(job["run_id_b"])
    
    status = "running"
    comparison = None
    
    if run_a and run_b:
        if run_a.status in ("completed", "failed", "cancelled") and run_b.status in ("completed", "failed", "cancelled"):
            status = "completed"
            
            if run_a.status == "completed" and run_b.status == "completed":
                try:
                    from glyph.grading.comparison import compare
                    path_a = Path(run_service.settings.artifacts_dir) / f"compare-{job_id}-a.jsonl"
                    path_b = Path(run_service.settings.artifacts_dir) / f"compare-{job_id}-b.jsonl"
                    if path_a.exists() and path_b.exists():
                        result = compare(path_a, path_b)
                        comparison = {
                            "common_cases": result.common_cases,
                            "improved": [c.model_dump() for c in result.improved],
                            "regressed": [c.model_dump() for c in result.regressed],
                            "unchanged": [c.model_dump() for c in result.unchanged],
                            "candidate_pass_rate": result.candidate_pass_rate,
                            "baseline_pass_rate": result.baseline_pass_rate,
                            "pass_rate_delta": result.pass_rate_delta,
                        }
                except Exception as e:
                    print(f"Error computing comparison: {e}")
            
    return CompareTargetsStatusResponse(
        status=status,
        run_id_a=job["run_id_a"],
        run_id_b=job["run_id_b"],
        comparison=comparison
    )
