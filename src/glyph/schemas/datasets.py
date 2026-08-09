"""Pydantic schemas for datasets API."""

from __future__ import annotations

from pydantic import BaseModel, Field


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


class ConversionPreviewResponse(BaseModel):
    """Response schema for a dataset conversion preview."""
    cases_converted: int = Field(description="Number of cases converted successfully")
    cases_quarantined: int = Field(description="Number of cases quarantined due to secrets or PII")
    cases_missing_expected: int = Field(description="Number of cases lacking an expected output")
    column_mapping: dict[str, str] = Field(description="Mapping of raw columns to Glyph fields")
    fuzzy_matches: list[str] = Field(description="List of fuzzy matching warnings")
    quarantine_file: str | None = Field(default=None, description="Path to the quarantine file if any")
    output_file: str | None = Field(default=None, description="Predicted path of the output file")
