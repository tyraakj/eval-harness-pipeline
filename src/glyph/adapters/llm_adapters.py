"""Built-in target adapters for evaluation.

This module provides factory functions for creating Target instances
using popular LLM providers and HTTP endpoints.
"""

from __future__ import annotations

from glyph.adapters.anthropic_adapter import create_anthropic_target
from glyph.adapters.http_adapter import create_http_target
from glyph.adapters.openai_adapter import create_openai_target

__all__ = [
    "create_anthropic_target",
    "create_http_target",
    "create_openai_target",
]
