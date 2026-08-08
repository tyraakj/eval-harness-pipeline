"""Business logic for graders.

This service layer handles grader-related operations including
listing available grader types.
"""

from __future__ import annotations

from fastapi import Depends

from glyph.api.settings import Settings, get_settings
from glyph.core.config import list_available_graders
from glyph.schemas.grader_schemas import GraderListResponse


class GraderService:
    """Service for managing graders."""

    def __init__(self, settings: Settings = Depends(get_settings)):
        self.settings = settings

    def list_graders(self) -> GraderListResponse:
        """List available grader types.
        
        Returns:
            Response containing available graders and their descriptions
        """
        graders = list_available_graders()
        return GraderListResponse(graders=graders)
