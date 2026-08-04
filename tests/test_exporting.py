from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from glyph.exporters.exporting import ExportDispatcher
from glyph.core.models import (
    EvalCase,
    ExportPolicy,
    Provenance,
    RunSummary,
    TrialRecord,
    TrialStatus,
)


class FlakyExporter:
    name = "flaky"

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def export_trial(
        self, case: EvalCase, record: TrialRecord, *, idempotency_key: str
    ) -> None:
        self.keys.append(idempotency_key)
        if len(self.keys) == 1:
            raise ConnectionError("retry")

    async def export_summary(
        self, summary: RunSummary, *, idempotency_key: str
    ) -> None:
        return None


class SlowExporter:
    name = "slow"

    async def export_trial(
        self, case: EvalCase, record: TrialRecord, *, idempotency_key: str
    ) -> None:
        await asyncio.Event().wait()

    async def export_summary(
        self, summary: RunSummary, *, idempotency_key: str
    ) -> None:
        return None


def record() -> TrialRecord:
    return TrialRecord(
        run_id="run",
        trial_id="trial",
        case_id="case",
        started_at=datetime.now(UTC),
        duration_ms=1,
        status=TrialStatus.PASSED,
        input_hash="sha256:test",
        provenance=Provenance(
            harness_version="1",
            code_revision="test",
            dataset_hash="sha256:dataset",
            target_hash="sha256:target",
        ),
    )


@pytest.mark.asyncio
async def test_export_retries_reuse_idempotency_key() -> None:
    exporter = FlakyExporter()
    dispatcher = ExportDispatcher(
        (exporter,),
        ExportPolicy(max_attempts=2, retry_backoff_seconds=0),
    )
    await dispatcher.start()
    await dispatcher.submit_trial(EvalCase(id="case", input={}), record())
    await dispatcher.close()

    assert len(exporter.keys) == 2
    assert exporter.keys[0] == exporter.keys[1]
    assert not dispatcher.errors


@pytest.mark.asyncio
async def test_export_timeout_is_bounded_and_recorded() -> None:
    dispatcher = ExportDispatcher(
        (SlowExporter(),),
        ExportPolicy(
            call_timeout_seconds=0.01,
            max_attempts=1,
            retry_backoff_seconds=0,
        ),
    )
    await dispatcher.start()
    await dispatcher.submit_trial(EvalCase(id="case", input={}), record())
    await dispatcher.close()

    assert dispatcher.errors
    assert "TimeoutError" in dispatcher.errors[0]