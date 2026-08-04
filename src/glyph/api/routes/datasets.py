"""Datasets API routes."""

from __future__ import annotations

from fastapi import APIRouter

from glyph.schemas.datasets import DatasetListResponse
from glyph.services.dataset_service import DatasetService

router = APIRouter()


@router.get("", response_model=DatasetListResponse)
async def list_datasets() -> DatasetListResponse:
    """List available datasets."""
    return DatasetService.list_datasets()
