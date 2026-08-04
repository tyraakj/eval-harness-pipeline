from __future__ import annotations

import importlib
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from glyph.core.models import TrialRecord, TrialStatus

_SYSTEM_ERROR_STATUSES = frozenset(
    {TrialStatus.ERROR, TrialStatus.TIMEOUT, TrialStatus.BUDGET_EXCEEDED}
)


class EvaluationTelemetry:
    def __init__(
        self,
        *,
        enabled: bool = False,
        instrumentation_name: str = "glyph",
        tracer_provider: Any | None = None,
        meter_provider: Any | None = None,
    ) -> None:
        self.enabled = enabled
        self.instrumentation_name = instrumentation_name
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider
        self._tracer: Any | None = None
        self._meter: Any | None = None
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}

    @contextmanager
    def span(self, name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        tracer = self._get_tracer()
        with tracer.start_as_current_span(
            name, record_exception=False, set_status_on_exception=False
        ) as current_span:
            for key, value in (attributes or {}).items():
                if value is not None:
                    current_span.set_attribute(key, value)
            try:
                yield
            except BaseException as error:
                self._record_span_error(current_span, error)
                raise

    @contextmanager
    def operation(
        self,
        name: str,
        *,
        metric_prefix: str,
        span_attributes: Mapping[str, Any] | None = None,
        metric_attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        attributes = dict(metric_attributes or {})
        self._counter(f"{metric_prefix}.requests").add(1, attributes)
        started_at = time.perf_counter()
        try:
            with self.span(name, span_attributes):
                yield
        except BaseException as error:
            error_attributes = {**attributes, "error.type": type(error).__name__}
            self._counter(f"{metric_prefix}.errors").add(1, error_attributes)
            raise
        finally:
            self._histogram(f"{metric_prefix}.duration").record(
                max(0.0, time.perf_counter() - started_at), attributes
            )

    def record_trial(self, record: TrialRecord, *, target_version: str) -> None:
        if not self.enabled:
            return
        attributes = {
            "evaluation.suite": record.suite.value,
            "evaluation.target.version": target_version,
            "evaluation.status": record.status.value,
            "evaluation.sandbox.provider": (
                record.sandbox.provider if record.sandbox is not None else "none"
            ),
        }
        self._counter("evaluation.trials").add(1, attributes)
        self._histogram("evaluation.trial.duration").record(
            record.duration_ms / 1_000, attributes
        )
        current_span = self._current_span()
        current_span.set_attribute("evaluation.status", record.status.value)
        if record.error_type is not None:
            current_span.set_attribute("error.type", record.error_type)
        if record.status in _SYSTEM_ERROR_STATUSES:
            error_attributes = {
                **attributes,
                "error.type": record.error_type or record.status.value,
            }
            self._counter("evaluation.trial.errors").add(1, error_attributes)
            self._set_span_error(current_span, record.error_message or record.status.value)

    def record_export_queue_error(self, *, exporter: str, error_type: str) -> None:
        if not self.enabled:
            return
        self._counter("evaluation.export.errors").add(
            1, {"evaluation.exporter": exporter, "error.type": error_type}
        )

    def _get_tracer(self) -> Any:
        if self._tracer is None:
            trace = self._import_otel("opentelemetry.trace")
            self._tracer = trace.get_tracer(
                self.instrumentation_name, tracer_provider=self.tracer_provider
            )
        return self._tracer

    def _get_meter(self) -> Any:
        if self._meter is None:
            metrics = self._import_otel("opentelemetry.metrics")
            self._meter = metrics.get_meter(
                self.instrumentation_name, meter_provider=self.meter_provider
            )
        return self._meter

    def _counter(self, name: str) -> Any:
        if name not in self._counters:
            self._counters[name] = self._get_meter().create_counter(
                name, unit="1"
            )
        return self._counters[name]

    def _histogram(self, name: str) -> Any:
        if name not in self._histograms:
            self._histograms[name] = self._get_meter().create_histogram(name, unit="s")
        return self._histograms[name]

    def _current_span(self) -> Any:
        return self._import_otel("opentelemetry.trace").get_current_span()

    def _record_span_error(self, span: Any, error: BaseException) -> None:
        span.record_exception(error)
        span.set_attribute("error.type", type(error).__name__)
        self._set_span_error(span, str(error))

    def _set_span_error(self, span: Any, description: str) -> None:
        status = self._import_otel("opentelemetry.trace.status")
        span.set_status(status.Status(status.StatusCode.ERROR, description[:2_000]))

    @staticmethod
    def _import_otel(module: str) -> Any:
        try:
            return importlib.import_module(module)
        except ImportError as error:
            raise RuntimeError(
                "OpenTelemetry is enabled but not installed; install the 'otel' extra"
            ) from error