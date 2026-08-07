from __future__ import annotations

from dataclasses import dataclass

from glyph.core.domain_models import Budget, EvalCase, SandboxSession


@dataclass(frozen=True, slots=True)
class RunContext:
    run_id: str
    trial_id: str
    budget: Budget
    sandbox: SandboxSession | None = None


class SandboxSessionError(Exception):
    """Raised when sandbox operations fail."""
    pass


class NoopSandboxProvider:
    """Compatibility provider that records the absence of process isolation."""

    name = "none"
    capabilities: frozenset[str] = frozenset()

    async def provision(self, case: EvalCase, context: RunContext) -> SandboxSession:
        return SandboxSession(
            id=context.trial_id,
            provider=self.name,
            isolation="none",
            metadata={"case_id": case.id},
        )

    async def reset(self, session: SandboxSession) -> None:
        return None

    async def destroy(self, session: SandboxSession) -> None:
        return None