from __future__ import annotations

import importlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from glyph.monitoring.telemetry import EvaluationTelemetry

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class OtelRuntime:
    telemetry: EvaluationTelemetry
    tracer_provider: Any
    meter_provider: Any

    def shutdown(self) -> None:
        """Flush batch telemetry before a short-lived evaluation process exits."""
        self.meter_provider.shutdown()
        self.tracer_provider.shutdown()


def configure_otel(
    *,
    service_name: str = "langgraph-eval-harness",
    endpoint: str = "http://localhost:4317",
    environment: str = "local",
    span_exporter: Any | None = None,
    metric_exporter: Any | None = None,
) -> OtelRuntime:
    if not service_name:
        raise ValueError("OpenTelemetry service name must not be empty")
    if not endpoint:
        raise ValueError("OpenTelemetry endpoint must not be empty")
    try:
        resources = importlib.import_module("opentelemetry.sdk.resources")
        sdk_trace = importlib.import_module("opentelemetry.sdk.trace")
        trace_export = importlib.import_module("opentelemetry.sdk.trace.export")
        sdk_metrics = importlib.import_module("opentelemetry.sdk.metrics")
        metric_export = importlib.import_module("opentelemetry.sdk.metrics.export")
        if span_exporter is None:
            otlp_trace = importlib.import_module(
                "opentelemetry.exporter.otlp.proto.http.trace_exporter"
            )
            span_exporter = otlp_trace.OTLPSpanExporter(
                endpoint=f"{endpoint}/v1/traces",
            )
        if metric_exporter is None:
            otlp_metrics = importlib.import_module(
                "opentelemetry.exporter.otlp.proto.http.metric_exporter"
            )
            metric_exporter = otlp_metrics.OTLPMetricExporter(
                endpoint=f"{endpoint}/v1/metrics",
            )
    except ImportError as error:
        raise RuntimeError(
            "OTLP export is enabled but unavailable; install the 'otel' extra"
        ) from error

    resource = resources.Resource.create(
        {
            "service.name": service_name,
            "deployment.environment.name": environment,
        }
    )
    tracer_provider = sdk_trace.TracerProvider(resource=resource)
    tracer_provider.add_span_processor(trace_export.BatchSpanProcessor(span_exporter))
    metric_reader = metric_export.PeriodicExportingMetricReader(metric_exporter)
    meter_provider = sdk_metrics.MeterProvider(
        resource=resource, metric_readers=[metric_reader]
    )
    return OtelRuntime(
        telemetry=EvaluationTelemetry(
            enabled=True,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        ),
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
    )


def configure_otel_from_env(
    environ: Mapping[str, str] | None = None,
) -> OtelRuntime | None:
    values = os.environ if environ is None else environ
    enabled = values.get("LANGGRAPH_EVAL_OTEL_ENABLED", "false").strip().lower()
    if enabled not in _TRUE_VALUES:
        return None
    return configure_otel(
        service_name=values.get("OTEL_SERVICE_NAME", "langgraph-eval-harness"),
        endpoint=values.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"),
        environment=values.get("OTEL_RESOURCE_ENVIRONMENT", "local"),
    )