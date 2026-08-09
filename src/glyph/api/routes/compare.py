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
