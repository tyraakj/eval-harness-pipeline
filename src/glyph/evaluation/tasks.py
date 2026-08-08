"""Re-export shim: glyph.evaluation.tasks → specialized_workers.evaluation.tasks."""
from __future__ import annotations

from glyph.specialized_workers.evaluation.tasks import celery_app, run_evaluation

__all__ = ["celery_app", "run_evaluation"]
