"""Business logic for datasets.

This service layer handles dataset-related operations including
listing available datasets from the filesystem.
"""

from __future__ import annotations

from pathlib import Path

from glyph.schemas.datasets import DatasetItem, DatasetListResponse


class DatasetService:
    """Service for managing datasets."""

    @staticmethod
    def list_datasets(datasets_dir: str = "datasets") -> DatasetListResponse:
        """List available datasets from the filesystem.
        
        Args:
            datasets_dir: Directory containing dataset files
            
        Returns:
            Response containing available datasets
        """
        datasets_path = Path(datasets_dir)
        if not datasets_path.exists():
            return DatasetListResponse(datasets=[])
        
        datasets = []
        for dataset_file in sorted(datasets_path.glob("*.jsonl")):
            datasets.append(DatasetItem(
                name=dataset_file.stem,
                path=str(dataset_file),
            ))
        
        return DatasetListResponse(datasets=datasets)
