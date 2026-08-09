"""Artifacts API routes."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from glyph.api.rate_limit import limiter
from glyph.api.settings import Settings, get_settings
from glyph.schemas.artifacts import ArtifactItem, ArtifactSummaryResponse
from glyph.schemas.runs import TrialListItem

router = APIRouter()


@router.get("", response_model=list[ArtifactItem])
@limiter.limit("120/minute")
async def list_artifacts(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> list[ArtifactItem]:
    """List all available artifacts."""
    artifacts_dir = Path(settings.artifacts_dir)
    if not artifacts_dir.exists():
        return []
        
    artifacts = []
    for p in artifacts_dir.glob("*.jsonl"):
        stat = p.stat()
        artifacts.append(ArtifactItem(
            name=p.name,
            path=str(p),
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime)
        ))
    
    return artifacts


@router.get("/{name}/summary", response_model=ArtifactSummaryResponse)
@limiter.limit("120/minute")
async def get_artifact_summary(
    request: Request,
    name: str,
    settings: Settings = Depends(get_settings),
) -> ArtifactSummaryResponse:
    """Get the RunSummary for an artifact."""
    artifact_path = Path(settings.artifacts_dir) / name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
        
    try:
        with open(artifact_path, encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            
        if not lines:
            raise HTTPException(status_code=422, detail="Artifact file is empty")
            
        # Run summary should be the last line
        summary_line = lines[-1]
        data = json.loads(summary_line)
        if data.get("event") != "run_complete":
            raise ValueError("No run_complete event found")
            
        return ArtifactSummaryResponse(**data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to load run summary: {e!s}")


@router.get("/{name}/trials", response_model=list[TrialListItem])
@limiter.limit("120/minute")
async def get_artifact_trials(
    request: Request,
    name: str,
    status: str | None = Query(None),
    suite: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    settings: Settings = Depends(get_settings),
) -> list[TrialListItem]:
    """Get trials from an artifact."""
    artifact_path = Path(settings.artifacts_dir) / name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
        
    trials = []
    skipped = 0
    
    try:
        with open(artifact_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                    
                data = json.loads(line)
                if data.get("event") == "trial_complete":
                    
                    if status and data.get("status") != status:
                        continue
                        
                    if suite and data.get("suite") != suite:
                        continue
                        
                    if skipped < offset:
                        skipped += 1
                        continue
                        
                    if len(trials) >= limit:
                        break
                        
                    mapped_data = {
                        "id": data.get("trial_id", ""),
                        "run_id": "",
                        "case_id": data.get("case_id", ""),
                        "suite": data.get("suite", ""),
                        "status": data.get("status", ""),
                        "score": data.get("score", 0.0),
                        "duration_ms": data.get("duration_ms", 0),
                        "started_at": data.get("timestamp", datetime.now().isoformat()),
                        "grades": data.get("grades", [])
                    }
                    trials.append(TrialListItem(**mapped_data))
        return trials
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse artifact trials: {e!s}")


@router.get("/{name}/trial/{case_id}", response_model=TrialListItem)
@limiter.limit("120/minute")
async def get_artifact_trial(
    request: Request,
    name: str,
    case_id: str,
    settings: Settings = Depends(get_settings),
) -> TrialListItem:
    """Get a specific trial from an artifact."""
    artifact_path = Path(settings.artifacts_dir) / name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
        
    try:
        with open(artifact_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                    
                data = json.loads(line)
                if data.get("event") == "trial_complete" and data.get("case_id") == case_id:
                    mapped_data = {
                        "id": data.get("trial_id", ""),
                        "run_id": "",
                        "case_id": data.get("case_id", ""),
                        "suite": data.get("suite", ""),
                        "status": data.get("status", ""),
                        "score": data.get("score", 0.0),
                        "duration_ms": data.get("duration_ms", 0),
                        "started_at": data.get("timestamp", datetime.now().isoformat()),
                        "grades": data.get("grades", [])
                    }
                    return TrialListItem(**mapped_data)
                    
        raise HTTPException(status_code=404, detail="Trial not found in artifact")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse artifact trials: {e!s}")

@router.get("/{name}/trace", response_model="TraceMetadataResponse")
@limiter.limit("60/minute")
async def get_artifact_trace(
    request: Request,
    name: str,
    settings: Settings = Depends(get_settings),
):
    """Get trace metadata from an artifact."""
    from glyph.schemas.artifacts import TraceMetadataResponse
    artifact_path = Path(settings.artifacts_dir) / name
    if not artifact_path.exists():
        raise HTTPException(status_code=404, detail="Artifact not found")
        
    trace_path = artifact_path.with_suffix('.trace.json')
    if not trace_path.exists():
        raise HTTPException(status_code=404, detail="Trace file not found")
        
    try:
        with open(trace_path, encoding="utf-8") as f:
            trace_data = json.load(f)
            
        steps_completed = trace_data.get("metadata", {}).get("steps_completed", 0)
        tests_processed = trace_data.get("metadata", {}).get("tests_processed", 0)
        shared_steps = trace_data.get("metadata", {}).get("shared_steps", 0)
        
        return TraceMetadataResponse(
            format="graph",
            steps_completed=steps_completed,
            tests_processed=tests_processed,
            shared_steps=shared_steps
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to parse trace: {e!s}")

