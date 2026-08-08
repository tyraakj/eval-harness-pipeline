"""Re-export shim: glyph.evaluation.definition → task_definitions."""
from __future__ import annotations

from glyph.specialized_workers.evaluation.task_definitions import EvaluationDefinition

__all__ = ["EvaluationDefinition"]
