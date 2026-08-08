from __future__ import annotations

import asyncio
from dataclasses import dataclass

from glyph.core.domain_models import EvalCase, ExportPolicy, RunSummary, TrialRecord
from glyph.monitoring.telemetry import EvaluationTelemetry
from glyph.security.contracts import EvaluationExporter
from glyph.utils import content_hash, sanitize_text


@dataclass(frozen=True, slots=True)
class _ExportJob:
    exporter: EvaluationExporter
    idempotency_key: str
    case: EvalCase | None = None
    record: TrialRecord | None = None
    summary: RunSummary | None = None


class ExportDispatcher:
    def __init__(
        self,
        exporters: tuple[EvaluationExporter, ...],
        policy: ExportPolicy,
        *,
        telemetry: EvaluationTelemetry | None = None,
    ) -> None:
        self.exporters = exporters
        self.policy = policy
        self.telemetry = telemetry or EvaluationTelemetry()
        self.errors: list[str] = []
        self._queue: asyncio.Queue[_ExportJob | None] = asyncio.Queue(
            maxsize=policy.queue_capacity
        )
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(), name=f"evaluation-export-{index}")
            for index in range(self.policy.worker_count)
        ]

    async def submit_trial(self, case: EvalCase, record: TrialRecord) -> None:
        for exporter in self.exporters:
            await self._enqueue(
                _ExportJob(
                    exporter=exporter,
                    idempotency_key=content_hash(
                        {"exporter": exporter.name, "trial_id": record.trial_id}
                    ),
                    case=case,
                    record=record,
                )
            )

    async def submit_summary(self, summary: RunSummary) -> None:
        for exporter in self.exporters:
            await self._enqueue(
                _ExportJob(
                    exporter=exporter,
                    idempotency_key=content_hash(
                        {"exporter": exporter.name, "run_id": summary.run_id}
                    ),
                    summary=summary,
                )
            )

    async def drain(self) -> None:
        await self._queue.join()

    async def close(self) -> None:
        await self.drain()
        for _ in self._workers:
            await self._queue.put(None)
        await asyncio.gather(*self._workers)
        self._workers.clear()

    async def _enqueue(self, job: _ExportJob) -> None:
        try:
            await asyncio.wait_for(
                self._queue.put(job), timeout=self.policy.enqueue_timeout_seconds
            )
        except TimeoutError:
            self.telemetry.record_export_queue_error(
                exporter=job.exporter.name, error_type="ExportQueueFull"
            )
            self._record_error(f"{job.exporter.name}: ExportQueueFull: enqueue timed out")

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job is None:
                    return
                await self._execute(job)
            finally:
                self._queue.task_done()

    async def _execute(self, job: _ExportJob) -> None:
        for attempt in range(1, self.policy.max_attempts + 1):
            try:
                kind = "trial" if job.record is not None else "summary"
                with self.telemetry.operation(
                    "evaluation.export",
                    metric_prefix="evaluation.export",
                    span_attributes={
                        "evaluation.exporter": job.exporter.name,
                        "evaluation.export.kind": kind,
                        "evaluation.export.attempt": attempt,
                    },
                    metric_attributes={
                        "evaluation.exporter": job.exporter.name,
                        "evaluation.export.kind": kind,
                    },
                ):
                    async with asyncio.timeout(self.policy.call_timeout_seconds):
                        if job.record is not None and job.case is not None:
                            await job.exporter.export_trial(
                                job.case,
                                job.record,
                                idempotency_key=job.idempotency_key,
                            )
                        elif job.summary is not None:
                            await job.exporter.export_summary(
                                job.summary, idempotency_key=job.idempotency_key
                            )
                        else:
                            raise TypeError("Invalid export job")
                return
            except asyncio.CancelledError:
                raise
            except Exception as error:
                if attempt < self.policy.max_attempts:
                    await asyncio.sleep(self.policy.retry_backoff_seconds * attempt)
                    continue
                message = (
                    f"{job.exporter.name}: {type(error).__name__}: "
                    f"{sanitize_text(str(error))}"
                )
                self._record_error(message[:2_000])

    def _record_error(self, message: str) -> None:
        if len(self.errors) < self.policy.max_recorded_errors:
            self.errors.append(message)