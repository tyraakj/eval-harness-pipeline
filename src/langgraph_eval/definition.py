from __future__ import annotations

from dataclasses import dataclass, field

from langgraph_eval.contracts import (
    EvaluationExporter,
    Grader,
    OutcomeCollector,
    SandboxProvider,
    Target,
)
from langgraph_eval.models import (
    Budget,
    EvaluationSuite,
    ExportPolicy,
    GraderPolicy,
    SandboxRequirements,
)
from langgraph_eval.telemetry import EvaluationTelemetry


@dataclass(frozen=True, slots=True)
class EvaluationDefinition:
    target: Target
    graders: tuple[Grader, ...]
    suite: EvaluationSuite = field(
        default_factory=lambda: EvaluationSuite(id="default", version="1.0.0")
    )
    outcome_collectors: tuple[OutcomeCollector, ...] = ()
    budget: Budget = field(default_factory=Budget)
    grader_policy: GraderPolicy = field(default_factory=GraderPolicy)
    repetitions: int = 1
    prompt_hashes: dict[str, str] = field(default_factory=dict)
    telemetry: EvaluationTelemetry = field(default_factory=EvaluationTelemetry)
    sandbox_provider: SandboxProvider | None = None
    sandbox_requirements: SandboxRequirements = field(default_factory=SandboxRequirements)
    exporters: tuple[EvaluationExporter, ...] = ()
    export_policy: ExportPolicy = field(default_factory=ExportPolicy)

    def __post_init__(self) -> None:
        if not self.graders:
            raise ValueError("An evaluation definition requires at least one grader")
        if self.repetitions < 1:
            raise ValueError("Repetitions must be at least one")
        grader_names = {grader.name for grader in self.graders}
        unknown_graders = set(self.suite.default_graders) - grader_names
        if unknown_graders:
            raise ValueError(f"Suite references unknown graders: {unknown_graders}")
