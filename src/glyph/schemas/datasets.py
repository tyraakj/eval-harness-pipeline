"""Pydantic schemas for datasets API."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class DatasetItem(BaseModel):
    """Schema for a single dataset item."""
    name: str = Field(description="Dataset name (filename without extension)")
    path: str = Field(description="Full path to the dataset file")
    case_count: int = Field(0, description="Number of cases in the dataset")


class DatasetListResponse(BaseModel):
    """Response schema for listing available datasets."""
    datasets: list[DatasetItem] = Field(description="List of available datasets")


class DatasetValidationResponse(BaseModel):
    """Response schema for dataset validation."""
    valid: bool
    case_count: int
    suite_counts: dict[str, int]
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
