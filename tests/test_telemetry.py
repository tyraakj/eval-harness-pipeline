from __future__ import annotations

from datetime import UTC, datetime

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from langgraph_eval.core.models import Provenance, TrialRecord, TrialStatus
from langgraph_eval.monitoring.telemetry import EvaluationTelemetry


def telemetry() -> tuple[EvaluationTelemetry, InMemoryMetricReader, InMemorySpanExporter]:
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return (
        EvaluationTelemetry(
            enabled=True,
            meter_provider=meter_provider,
            tracer_provider=tracer_provider,
        ),
        metric_reader,
        span_exporter,
    )


def record(status: TrialStatus, *, error_type: str | None = None) -> TrialRecord:
    return TrialRecord(
        run_id="run-unbounded",
        trial_id="trial-unbounded",
        case_id="case-unbounded",
        started_at=datetime.now(UTC),
        duration_ms=1_250,
        status=status,
        input_hash="sha256:test",
        error_type=error_type,
        error_message="terminal failure" if error_type is not None else None,
        provenance=Provenance(
            harness_version="1",
            code_revision="test",
            dataset_hash="sha256:dataset",
            target_hash="sha256:target",
        ),
    )


def metric_points(reader: InMemoryMetricReader, name: str) -> tuple[object, ...]:
    metrics_data = reader.get_metrics_data()
    return tuple(
        point
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == name
        for point in metric.data.data_points
    )


def test_trial_red_metrics_use_bounded_attributes() -> None:
    evaluation_telemetry, metric_reader, _ = telemetry()

    with evaluation_telemetry.span("evaluation.trial"):
        evaluation_telemetry.record_trial(record(TrialStatus.FAILED), target_version="v1")
    with evaluation_telemetry.span("evaluation.trial"):
        evaluation_telemetry.record_trial(
            record(TrialStatus.TIMEOUT, error_type="TimeoutError"), target_version="v1"
        )

    trial_points = metric_points(metric_reader, "evaluation.trials")
    error_points = metric_points(metric_reader, "evaluation.trial.errors")
    duration_points = metric_points(metric_reader, "evaluation.trial.duration")

    assert sum(point.value for point in trial_points) == 2  # type: ignore[attr-defined]
    assert sum(point.value for point in error_points) == 1  # type: ignore[attr-defined]
    assert sum(point.count for point in duration_points) == 2  # type: ignore[attr-defined]
    assert sum(point.sum for point in duration_points) == pytest.approx(2.5)  # type: ignore[attr-defined]
    for point in (*trial_points, *error_points, *duration_points):
        assert "evaluation.run.id" not in point.attributes  # type: ignore[attr-defined]
        assert "evaluation.trial.id" not in point.attributes  # type: ignore[attr-defined]
        assert "evaluation.case.id" not in point.attributes  # type: ignore[attr-defined]


def test_operation_records_rate_error_duration_and_span_exception() -> None:
    evaluation_telemetry, metric_reader, span_exporter = telemetry()

    with pytest.raises(ValueError, match="invalid result"):
        with evaluation_telemetry.operation(
            "evaluation.grader",
            metric_prefix="evaluation.grader",
            span_attributes={"evaluation.trial.id": "trace-only"},
            metric_attributes={"evaluation.grader.name": "schema"},
        ):
            raise ValueError("invalid result")

    request_points = metric_points(metric_reader, "evaluation.grader.requests")
    error_points = metric_points(metric_reader, "evaluation.grader.errors")
    duration_points = metric_points(metric_reader, "evaluation.grader.duration")
    assert sum(point.value for point in request_points) == 1  # type: ignore[attr-defined]
    assert sum(point.value for point in error_points) == 1  # type: ignore[attr-defined]
    assert sum(point.count for point in duration_points) == 1  # type: ignore[attr-defined]
    assert error_points[0].attributes["error.type"] == "ValueError"  # type: ignore[attr-defined]
    assert "evaluation.trial.id" not in request_points[0].attributes  # type: ignore[attr-defined]

    span = span_exporter.get_finished_spans()[0]
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes is not None
    assert span.attributes["error.type"] == "ValueError"
    assert span.events[0].name == "exception"