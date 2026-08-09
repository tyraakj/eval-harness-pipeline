"""Business logic for datasets.

This service layer handles dataset-related operations including
listing available datasets from the filesystem.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import Depends

from glyph.api.settings import Settings, get_settings
from glyph.core.domain_models import EvalCase
from glyph.schemas.datasets import DatasetItem, DatasetListResponse, DatasetValidationResponse


class DatasetService:
    """Service for managing datasets."""

    def __init__(self, settings: Settings = Depends(get_settings)):
        self.settings = settings

    def list_datasets(self) -> DatasetListResponse:
        """List available datasets from the filesystem."""
        datasets_path = Path(self.settings.datasets_dir)
        if not datasets_path.exists():
            return DatasetListResponse(datasets=[])
        
        datasets = []
        for dataset_file in sorted(datasets_path.glob("*.jsonl")):
            case_count = self._count_cases(dataset_file)
            datasets.append(DatasetItem(
                name=dataset_file.stem,
                path=str(dataset_file),
                case_count=case_count,
            ))
        
        return DatasetListResponse(datasets=datasets)
    
    def _count_cases(self, file_path: Path) -> int:
        count = 0
        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        count += 1
        except Exception:
            pass
        return count

    def get_cases(self, name: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]] | None:
        """Get paginated cases from a dataset."""
        dataset_path = Path(self.settings.datasets_dir) / f"{name}.jsonl"
        if not dataset_path.exists():
            return None
            
        cases = []
        try:
            with open(dataset_path, encoding="utf-8") as f:
                for i, line in enumerate(f):
                    if i < offset:
                        continue
                    if i >= offset + limit:
                        break
                    if line.strip():
                        cases.append(json.loads(line))
        except Exception:
            return None
            
        return cases

    def delete_dataset(self, name: str) -> bool:
        """Delete a dataset file."""
        dataset_path = Path(self.settings.datasets_dir) / f"{name}.jsonl"
        if not dataset_path.exists():
            return False
            
        dataset_path.unlink()
        return True
        
    def validate_dataset(self, name: str) -> DatasetValidationResponse | None:
        """Validate a dataset."""
        dataset_path = Path(self.settings.datasets_dir) / f"{name}.jsonl"
        if not dataset_path.exists():
            return None
            
        errors = []
        warnings = []
        case_count = 0
        suite_counts = {}
        tagged_cases = 0
        seen_ids = set()
        
        try:
            with open(dataset_path, encoding="utf-8") as f:
                for line_idx, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                        
                    case_count += 1
                    try:
                        data = json.loads(line)
                        case = EvalCase.model_validate(data)
                        
                        # Check duplicates
                        if case.id in seen_ids:
                            errors.append(f"Duplicate case ID '{case.id}' on line {line_idx + 1}")
                        seen_ids.add(case.id)
                        
                        # Count suites
                        suite = case.suite
                        suite_counts[suite] = suite_counts.get(suite, 0) + 1
                        
                        # Count tags
                        if case.tags:
                            tagged_cases += 1
                            
                    except Exception as e:
                        errors.append(f"Line {line_idx + 1}: failed to parse as EvalCase - {e!s}")
                        
        except Exception as e:
            errors.append(f"Failed to read file: {e!s}")
            
        if case_count > 0 and (tagged_cases / case_count) < 0.5:
            warnings.append(f"Only {tagged_cases}/{case_count} tests have tags (< 50%)")
            
        return DatasetValidationResponse(
            valid=len(errors) == 0,
            case_count=case_count,
            suite_counts=suite_counts,
            errors=errors,
            warnings=warnings
        )
