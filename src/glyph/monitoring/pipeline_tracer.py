"""Internal pipeline tracing for Glyph's evaluation workflow."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import uuid4

from glyph.core.models import EvalCase, TrialRecord


class PipelineStage(StrEnum):
    """Stages in the evaluation pipeline."""
    DATASET_LOAD = "dataset_load"
    SANDBOX_PROVISION = "sandbox_provision"
    TARGET_EXECUTE = "target_execute"
    OUTCOME_COLLECT = "outcome_collect"
    GRADING = "grading"
    ARTIFACT_WRITE = "artifact_write"
    SANDBOX_DESTROY = "sandbox_destroy"
    EXPORT_DISPATCH = "export_dispatch"
    RELEASE_GATE = "release_gate"
    BASELINE_COMPARE = "baseline_compare"


@dataclass
class PipelineSpan:
    """A single span in the pipeline trace."""
    span_id: str = field(default_factory=lambda: str(uuid4()))
    parent_id: str | None = None
    stage: PipelineStage = PipelineStage.TARGET_EXECUTE
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    duration_ms: float | None = None
    status: str = "started"
    error: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)

    def finish(self, status: str = "completed", error: str | None = None) -> None:
        """Mark the span as finished."""
        self.finished_at = datetime.now(UTC)
        self.duration_ms = (self.finished_at - self.started_at).total_seconds() * 1000
        self.status = status
        self.error = error

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Add an event to this span."""
        self.events.append({
            "name": name,
            "timestamp": datetime.now(UTC).isoformat(),
            "attributes": attributes or {},
        })


@dataclass
class PipelineTrace:
    """A complete trace of an evaluation pipeline execution."""
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    run_id: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    spans: list[PipelineSpan] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def start_span(
        self,
        stage: PipelineStage,
        parent_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> PipelineSpan:
        """Start a new span in this trace."""
        span = PipelineSpan(
            parent_id=parent_id,
            stage=stage,
            attributes=attributes or {},
        )
        self.spans.append(span)
        return span

    def finish(self) -> None:
        """Mark the entire trace as finished."""
        self.finished_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert trace to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": (
                (self.finished_at - self.started_at).total_seconds() * 1000
                if self.finished_at
                else None
            ),
            "spans": [
                {
                    "span_id": s.span_id,
                    "parent_id": s.parent_id,
                    "stage": s.stage.value,
                    "started_at": s.started_at.isoformat(),
                    "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                    "duration_ms": s.duration_ms,
                    "status": s.status,
                    "error": s.error,
                    "attributes": s.attributes,
                    "events": s.events,
                }
                for s in self.spans
            ],
            "metadata": self.metadata,
        }


class PipelineTracer:
    """Internal tracer for Glyph's evaluation pipeline."""

    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = output_path
        self.current_trace: PipelineTrace | None = None
        self._span_stack: list[PipelineSpan] = []

    @asynccontextmanager
    async def trace_run(self, run_id: str, metadata: dict[str, Any] | None = None) -> AsyncIterator[PipelineTrace]:
        """Async context manager for tracing a complete evaluation run."""
        self.current_trace = PipelineTrace(run_id=run_id, metadata=metadata or {})
        try:
            yield self.current_trace
        finally:
            self.current_trace.finish()
            if self.output_path:
                self._write_trace()

    @asynccontextmanager
    async def span(
        self,
        stage: PipelineStage,
        attributes: dict[str, Any] | None = None,
    ) -> AsyncIterator[PipelineSpan]:
        """Async context manager for tracing a single pipeline stage."""
        if not self.current_trace:
            raise RuntimeError("No active trace - use trace_run() first")

        parent_id = self._span_stack[-1].span_id if self._span_stack else None
        span = self.current_trace.start_span(stage, parent_id, attributes)
        self._span_stack.append(span)

        try:
            yield span
            span.finish(status="completed")
        except Exception as e:
            span.finish(status="error", error=str(e))
            raise
        finally:
            self._span_stack.pop()

    def record_case_start(self, case: EvalCase, repetition: int) -> None:
        """Record the start of a case evaluation."""
        if not self.current_trace:
            return

        current_span = self._span_stack[-1] if self._span_stack else None
        if current_span:
            current_span.add_event(
                "case_start",
                {
                    "case_id": case.id,
                    "suite": case.suite.value,
                    "repetition": repetition,
                    "tags": list(case.tags),
                },
            )

    def record_case_complete(self, record: TrialRecord) -> None:
        """Record the completion of a case evaluation."""
        if not self.current_trace:
            return

        current_span = self._span_stack[-1] if self._span_stack else None
        if current_span:
            current_span.add_event(
                "case_complete",
                {
                    "case_id": record.case_id,
                    "status": record.status.value,
                    "duration_ms": record.duration_ms,
                    "score": record.score,
                },
            )

    def _write_trace(self) -> None:
        """Write the trace to disk."""
        if not self.output_path or not self.current_trace:
            return

        # Handle both directory and file paths
        if self.output_path.exists() and self.output_path.is_file():
            trace_dir = self.output_path.parent
        else:
            trace_dir = self.output_path
        
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_dir / f"trace-{self.current_trace.run_id}.json"
        trace_file.write_text(json.dumps(self.current_trace.to_dict(), indent=2) + "\n")

    def get_trace_summary(self) -> dict[str, Any]:
        """Get a summary of the current trace."""
        if not self.current_trace:
            return {}

        spans_by_stage = {}
        for span in self.current_trace.spans:
            stage = span.stage.value
            if stage not in spans_by_stage:
                spans_by_stage[stage] = {
                    "count": 0,
                    "total_duration_ms": 0,
                    "errors": 0,
                }
            spans_by_stage[stage]["count"] += 1
            if span.duration_ms:
                spans_by_stage[stage]["total_duration_ms"] += span.duration_ms
            if span.status == "error":
                spans_by_stage[stage]["errors"] += 1

        return {
            "trace_id": self.current_trace.trace_id,
            "run_id": self.current_trace.run_id,
            "total_spans": len(self.current_trace.spans),
            "total_duration_ms": (
                (self.current_trace.finished_at - self.current_trace.started_at).total_seconds() * 1000
                if self.current_trace.finished_at
                else 0
            ),
            "spans_by_stage": spans_by_stage,
            "total_errors": sum(s["errors"] for s in spans_by_stage.values()),
        }
