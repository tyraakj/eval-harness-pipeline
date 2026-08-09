from __future__ import annotations

from typing import Protocol

from pydantic import JsonValue

from glyph.core.domain_models import (
    EvalCase,
    Grade,
    OutcomeObservation,
    RunSummary,
    SandboxRunResult,
    SandboxSession,
    TargetResult,
    TrialRecord,
)
from glyph.security.live_sandbox import RunContext


class SandboxProvider(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> frozenset[str]: ...

    async def provision(self, case: EvalCase, context: RunContext) -> SandboxSession: ...

    async def reset(self, session: SandboxSession) -> None: ...

    async def destroy(self, session: SandboxSession) -> None: ...

    async def run(
        self,
        session: SandboxSession,
        argv: list[str],
        env: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> SandboxRunResult:
        raise NotImplementedError

    async def read(
        self,
        session: SandboxSession,
        path: str,
    ) -> bytes:
        raise NotImplementedError

    async def write(
        self,
        session: SandboxSession,
        path: str,
        data: bytes,
    ) -> None:
        raise NotImplementedError


class EvaluationExporter(Protocol):
    @property
    def name(self) -> str: ...

    async def export_trial(
        self, case: EvalCase, record: TrialRecord, *, idempotency_key: str
    ) -> None: ...

    async def export_summary(
        self, summary: RunSummary, *, idempotency_key: str
    ) -> None: ...


class OnlineCostLedger(Protocol):
    async def try_reserve(self, period: str, amount_usd: float, limit_usd: float) -> bool: ...


class Target(Protocol):
    @property
    def version(self) -> str: ...

    async def execute(self, case: EvalCase, context: RunContext) -> TargetResult: ...


class Grader(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade: ...


class OutcomeCollector(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def collect(
        self, case: EvalCase, result: TargetResult, context: RunContext
    ) -> JsonValue | OutcomeObservation: ...
