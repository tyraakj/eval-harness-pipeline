"""Business logic for graders.

This service layer handles grader-related operations including
listing available grader types.
"""

from __future__ import annotations

from glyph.core.config import list_available_graders
from glyph.schemas.graders import GraderListResponse


class GraderService:
    """Service for managing graders."""

    @staticmethod
    def list_graders() -> GraderListResponse:
        """List available grader types.
        
        Returns:
            Response containing available graders and their descriptions
        """
        graders = list_available_graders()
        return GraderListResponse(graders=graders)
