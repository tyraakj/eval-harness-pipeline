"""FastAPI server entry point for running the application.

This module allows the FastAPI server to be run directly with:
    python -m langgraph_eval.api
"""

from __future__ import annotations

import uvicorn

from langgraph_eval.api.main import app

if __name__ == "__main__":
    uvicorn.run(
        "langgraph_eval.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
