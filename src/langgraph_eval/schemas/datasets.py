"""Pydantic schemas for datasets API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DatasetItem(BaseModel):
    """Schema for a single dataset item."""
    name: str = Field(description="Dataset name (filename without extension)")
    path: str = Field(description="Full path to the dataset file")


class DatasetListResponse(BaseModel):
    """Response schema for listing available datasets."""
    datasets: list[DatasetItem] = Field(description="List of available datasets")
