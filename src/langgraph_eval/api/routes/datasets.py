"""Datasets API routes."""

from __future__ import annotations

from fastapi import APIRouter

from langgraph_eval.schemas.datasets import DatasetListResponse
from langgraph_eval.services.dataset_service import DatasetService

router = APIRouter()


@router.get("", response_model=DatasetListResponse)
async def list_datasets() -> DatasetListResponse:
    """List available datasets."""
    return DatasetService.list_datasets()
