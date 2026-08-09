"""Datasets API routes."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from glyph.api.rate_limit import limiter
from glyph.schemas.datasets import DatasetItem, DatasetListResponse, DatasetValidationResponse, ConversionPreviewResponse
from glyph.services.dataset_service import DatasetService
from glyph.utils.converters import detect_format, parse_source, map_columns, generate_id, sanitize_case, SourceFormat
from glyph.specialized_workers.policy_registry import DEFAULT_SECRET_PATTERNS
from glyph.generation import PIIScanner
import shutil

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


# Temporary cache for previewed conversions (in a real app, use Redis/DB)
_conversion_cache = {}


@router.post("/convert", response_model=ConversionPreviewResponse)
@limiter.limit("5/minute")
async def preview_convert(
    request: Request,
    file: UploadFile = File(...),
    format: str | None = None,
    suite: str | None = None,
    id_prefix: str | None = None,
    dataset_service: DatasetService = Depends(DatasetService)
) -> ConversionPreviewResponse:
    """Preview a dataset conversion without writing the final output."""
    temp_dir = Path(dataset_service.settings.datasets_dir) / "drafts"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"temp_{file.filename}"
    
    content = await file.read()
    temp_path.write_bytes(content)
    
    source_format = SourceFormat(format) if format else detect_format(temp_path)
    try:
        raw_rows = parse_source(temp_path, source_format)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse source: {e}")
        
    mapped_cases, mapping, fuzzy_matches = map_columns(raw_rows, source_format)
    
    prefix = id_prefix or file.filename.rsplit(".", 1)[0]
    
    scanner = PIIScanner()
    
    cases_converted = 0
    cases_quarantined = 0
    cases_missing = 0
    
    valid_cases = []
    quarantined_cases = []
    
    for i, case in enumerate(mapped_cases):
        case["id"] = generate_id(case, prefix, i + 1)
        if suite:
            case["suite"] = suite
        elif "suite" not in case:
            case["suite"] = "capability"
            
        quarantine_reason = sanitize_case(case, scanner, DEFAULT_SECRET_PATTERNS)
        
        if quarantine_reason:
            cases_quarantined += 1
            case["_quarantine_reason"] = quarantine_reason
            quarantined_cases.append(case)
        else:
            if "expected" not in case or not case["expected"]:
                cases_missing += 1
                case["expected"] = {}
                case["metadata"]["requires_human_expected"] = True
            cases_converted += 1
            valid_cases.append(case)
            
    quarantine_file = None
    if quarantined_cases:
        q_path = temp_dir / f"{prefix}-quarantined.jsonl"
        with open(q_path, "w", encoding="utf-8") as f:
            for qc in quarantined_cases:
                f.write(json.dumps(qc) + "\n")
        quarantine_file = str(q_path)
        
    output_file_name = f"{prefix}-converted.jsonl"
    
    # Save to cache
    _conversion_cache[output_file_name] = valid_cases
    
    return ConversionPreviewResponse(
        cases_converted=cases_converted,
        cases_quarantined=cases_quarantined,
        cases_missing_expected=cases_missing,
        column_mapping=mapping,
        fuzzy_matches=fuzzy_matches,
        quarantine_file=quarantine_file,
        output_file=output_file_name
    )


class ConfirmRequest(BaseModel):
    output_file: str


@router.post("/convert/confirm", response_model=DatasetItem)
@limiter.limit("5/minute")
async def confirm_convert(
    request: Request,
    payload: ConfirmRequest,
    dataset_service: DatasetService = Depends(DatasetService)
) -> DatasetItem:
    """Confirm and write the converted dataset."""
    output_file = payload.output_file
    if output_file not in _conversion_cache:
        raise HTTPException(status_code=404, detail="Conversion session expired or not found")
        
    cases = _conversion_cache.pop(output_file)
    output_path = Path(dataset_service.settings.datasets_dir) / output_file
    
    with open(output_path, "w", encoding="utf-8") as f:
        # Sort by ID for stable diffs
        cases.sort(key=lambda x: x.get("id", ""))
        for case in cases:
            f.write(json.dumps(case) + "\n")
            
    return DatasetItem(
        name=output_file[:-6],
        path=str(output_path),
        case_count=len(cases)
    )

