"""Datasets API routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile

from glyph.api.rate_limit import limiter
from glyph.schemas.datasets import DatasetItem, DatasetListResponse, DatasetValidationResponse
from glyph.services.dataset_service import DatasetService

router = APIRouter()


@router.get("", response_model=DatasetListResponse)
@limiter.limit("120/minute")
async def list_datasets(
    request: Request,
    dataset_service: DatasetService = Depends(DatasetService)
) -> DatasetListResponse:
    """List available datasets."""
    return dataset_service.list_datasets()


@router.get("/{name}/cases")
@limiter.limit("120/minute")
async def get_dataset_cases(
    request: Request,
    name: str,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    dataset_service: DatasetService = Depends(DatasetService)
):
    """Get cases from a dataset."""
    cases = dataset_service.get_cases(name, limit=limit, offset=offset)
    if cases is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"cases": cases}


@router.post("", response_model=DatasetItem)
@limiter.limit("5/minute")
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    dataset_service: DatasetService = Depends(DatasetService)
) -> DatasetItem:
    """Upload a new dataset."""
    if not file.filename.endswith(".jsonl"):
        raise HTTPException(status_code=422, detail="Only JSONL files are supported")
        
    dataset_name = file.filename[:-6]
    dataset_path = Path(dataset_service.settings.datasets_dir) / file.filename
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Read the file and validate it has unique IDs and is valid JSONL
    seen_ids = set()
    content = await file.read()
    lines = content.decode("utf-8").splitlines()
    
    for line_idx, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if "id" in data:
                if data["id"] in seen_ids:
                    raise HTTPException(status_code=422, detail=f"Duplicate case ID '{data['id']}'")
                seen_ids.add(data["id"])
            else:
                raise HTTPException(status_code=422, detail=f"Missing 'id' field in case on line {line_idx+1}")
        except json.JSONDecodeError:
            raise HTTPException(status_code=422, detail=f"Invalid JSON on line {line_idx+1}")
            
    # Write to disk
    dataset_path.write_bytes(content)
    
    return DatasetItem(
        name=dataset_name,
        path=str(dataset_path),
        case_count=len(seen_ids)
    )


@router.delete("/{name}")
@limiter.limit("120/minute")
async def delete_dataset(
    request: Request,
    name: str,
    dataset_service: DatasetService = Depends(DatasetService)
):
    """Delete a dataset."""
    success = dataset_service.delete_dataset(name)
    if not success:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"deleted": True}


@router.get("/{name}/validate", response_model=DatasetValidationResponse)
@limiter.limit("120/minute")
async def validate_dataset(
    request: Request,
    name: str,
    dataset_service: DatasetService = Depends(DatasetService)
) -> DatasetValidationResponse:
    """Validate a dataset."""
    validation = dataset_service.validate_dataset(name)
    if validation is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return validation
