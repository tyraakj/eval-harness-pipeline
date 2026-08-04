"""FastAPI server entry point for running the application.

This module allows the FastAPI server to be run directly with:
    python -m glyph.api
"""

from __future__ import annotations

import uvicorn

from glyph.api.main import app

if __name__ == "__main__":
    uvicorn.run(
        "glyph.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
