from __future__ import annotations

from io import StringIO

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
from opentelemetry.sdk.trace.export import ConsoleSpanExporter

from langgraph_eval.monitoring.observability import configure_otel, configure_otel_from_env


def test_otlp_runtime_exports_and_flushes_batch_telemetry() -> None:
    span_output = StringIO()
    metric_output = StringIO()
    runtime = configure_otel(
        span_exporter=ConsoleSpanExporter(out=span_output),
        metric_exporter=ConsoleMetricExporter(out=metric_output),
    )

    with runtime.telemetry.operation(
        "evaluation.target",
        metric_prefix="evaluation.target",
        metric_attributes={"evaluation.suite": "capability"},
    ):
        pass
    runtime.shutdown()

    assert "evaluation.target" in span_output.getvalue()
    assert "evaluation.target.requests" in metric_output.getvalue()
    assert "evaluation.target.duration" in metric_output.getvalue()


def test_environment_bootstrap_is_opt_in() -> None:
    assert configure_otel_from_env({}) is None
    assert configure_otel_from_env({"LANGGRAPH_EVAL_OTEL_ENABLED": "off"}) is None