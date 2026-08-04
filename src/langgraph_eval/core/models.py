from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TrialStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    TIMEOUT = "timeout"
    BUDGET_EXCEEDED = "budget_exceeded"


class OnlineEvaluationStatus(StrEnum):
    DISABLED = "disabled"
    NOT_SAMPLED = "not_sampled"
    REJECTED = "rejected"
    BUDGET_EXCEEDED = "budget_exceeded"
    EVALUATED = "evaluated"
    ERROR = "error"


class SuiteType(StrEnum):
    CAPABILITY = "capability"
    REGRESSION = "regression"
    SECURITY = "security"


class SecurityDecision(StrEnum):
    ALLOW = "allow"
    BLOCK = "block"


class RetrievalExpectation(FrozenModel):
    relevant_source_ids: frozenset[str] = Field(min_length=1)


class SecurityExpectation(FrozenModel):
    decision: SecurityDecision
    prohibited_tools: frozenset[str] = Field(default_factory=frozenset)
    required_controls: frozenset[str] = Field(default_factory=frozenset)


class EvaluationSuite(FrozenModel):
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str = Field(min_length=1)
    description: str = ""
    default_graders: frozenset[str] = Field(default_factory=frozenset)
    tracked_metrics: frozenset[str] = Field(default_factory=frozenset)


class Budget(FrozenModel):
    timeout_seconds: float = Field(default=60.0, gt=0, le=3600)
    max_tool_calls: int = Field(default=20, ge=0, le=1000)
    max_output_chars: int = Field(default=100_000, ge=1)
    max_concurrency: int = Field(default=4, ge=1, le=100)
    max_judge_cost_usd: float | None = Field(default=None, ge=0)
    max_outcome_bytes: int = Field(default=100_000, ge=1_024, le=10_000_000)
    max_grade_evidence_bytes: int = Field(default=100_000, ge=1_024, le=10_000_000)
    max_trial_artifact_bytes: int = Field(default=1_000_000, ge=10_000, le=100_000_000)


class SandboxSession(FrozenModel):
    id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    isolation: str = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class SandboxCleanup(FrozenModel):
    attempted: bool = False
    succeeded: bool = False
    error_type: str | None = None
    error_message: str | None = None


class SandboxRequirements(FrozenModel):
    required: bool = True
    capabilities: frozenset[str] = Field(default_factory=frozenset)


class EvalCase(FrozenModel):
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    input: dict[str, Any]
    expected: dict[str, Any] = Field(default_factory=dict)
    suite: SuiteType = SuiteType.CAPABILITY
    graders: frozenset[str] = Field(default_factory=frozenset)
    tracked_metrics: frozenset[str] = Field(default_factory=frozenset)
    tags: frozenset[str] = Field(default_factory=frozenset)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class TranscriptCapturePolicy(FrozenModel):
    capture_messages: bool = False
    capture_streaming_chunks: bool = False
    capture_tool_inputs: bool = False
    capture_tool_outputs: bool = False
    tool_payload_allowlist: frozenset[str] = Field(default_factory=frozenset)
    max_event_bytes: int = Field(default=8_192, ge=256, le=1_000_000)
    max_total_bytes: int = Field(default=250_000, ge=1_024, le=10_000_000)


class OnlineEvaluationPolicy(FrozenModel):
    enabled: bool = False
    privacy_review_id: str | None = None
    sampling_rate: float = Field(default=0, ge=0, le=1)
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    maximum_monthly_cost_usd: float | None = Field(default=None, gt=0)
    allowed_project: str | None = None
    evaluator_timeout_seconds: float = Field(default=30.0, gt=0, le=300)

    @model_validator(mode="after")
    def require_production_controls(self) -> OnlineEvaluationPolicy:
        if not self.enabled:
            return self
        missing = [
            name
            for name, value in (
                ("privacy_review_id", self.privacy_review_id),
                ("retention_days", self.retention_days),
                ("maximum_monthly_cost_usd", self.maximum_monthly_cost_usd),
                ("allowed_project", self.allowed_project),
            )
            if value is None
        ]
        if self.sampling_rate <= 0:
            missing.append("sampling_rate")
        if missing:
            raise ValueError(
                "Online evaluation requires approved controls: " + ", ".join(missing)
            )
        return self


class OnlineEvaluationDecision(FrozenModel):
    trace_id: str
    status: OnlineEvaluationStatus
    sampled: bool
    reason: str
    grades: tuple[Grade, ...] = ()
    reserved_cost_usd: float = Field(default=0, ge=0)


class ReleasePolicy(FrozenModel):
    """Policy for determining whether a release is allowed."""
    require_deterministic: bool = True
    require_regression_check: bool = False
    require_judge: bool = False
    
    # Deterministic evaluation requirements
    minimum_overall_pass_rate: float = Field(default=1.0, ge=0, le=1)
    minimum_capability_pass_rate: float = Field(default=0.9, ge=0, le=1)
    minimum_regression_pass_rate: float = Field(default=1.0, ge=0, le=1)
    minimum_security_pass_rate: float = Field(default=1.0, ge=0, le=1)
    maximum_error_rate: float = Field(default=0.0, ge=0, le=1)
    
    # Regression check requirements
    maximum_regressions: int = Field(default=0, ge=0)
    minimum_pass_rate_delta: float = Field(default=0.0, ge=-1.0, le=1.0)
    
    # Judge evaluation requirements
    minimum_judge_score: float = Field(default=0.7, ge=0, le=1)
    maximum_judge_cost_usd: float = Field(default=10.0, ge=0)
    
    @model_validator(mode="after")
    def validate_policy(self) -> ReleasePolicy:
        if self.require_regression_check and not self.require_deterministic:
            raise ValueError("Regression check requires deterministic evaluation")
        if self.require_judge and not self.require_deterministic:
            raise ValueError("Judge evaluation requires deterministic evaluation")
        return self


class ReleaseDecision(FrozenModel):
    """Decision on whether a release is allowed with detailed rationale."""
    allowed: bool
    reason: str
    deterministics_passed: bool = False
    deterministics_rationale: str = ""
    regression_passed: bool = True
    regression_rationale: str = ""
    judge_passed: bool = True
    judge_rationale: str = ""
    
    # Summary metrics for audit trail
    overall_pass_rate: float = Field(default=0, ge=0, le=1)
    capability_pass_rate: float = Field(default=0, ge=0, le=1)
    regression_pass_rate: float = Field(default=0, ge=0, le=1)
    security_pass_rate: float = Field(default=0, ge=0, le=1)
    error_rate: float = Field(default=0, ge=0, le=1)
    
    regression_count: int = Field(default=0, ge=0)
    pass_rate_delta: float = Field(default=0, ge=-1.0, le=1.0)
    
    judge_score: float = Field(default=0, ge=0, le=1)
    judge_cost_usd: float = Field(default=0, ge=0)


class ExportPolicy(FrozenModel):
    queue_capacity: int = Field(default=100, ge=1, le=100_000)
    worker_count: int = Field(default=2, ge=1, le=32)
    enqueue_timeout_seconds: float = Field(default=1.0, gt=0, le=60)
    call_timeout_seconds: float = Field(default=10.0, gt=0, le=300)
    max_attempts: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=0.25, ge=0, le=30)
    max_recorded_errors: int = Field(default=100, ge=1, le=10_000)


class TrajectoryEvent(FrozenModel):
    sequence: int = Field(ge=0)
    kind: str
    name: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    duration_ms: int | None = Field(default=None, ge=0)
    run_id: str | None = None
    parent_run_id: str | None = None
    data: dict[str, JsonValue] = Field(default_factory=dict)


class LoopIteration(FrozenModel):
    index: int = Field(ge=0)
    node: str = Field(min_length=1)
    outcome: str
    state_hash: str | None = None
    duration_ms: int = Field(default=0, ge=0)


class LoopObservation(FrozenModel):
    iterations: tuple[LoopIteration, ...] = ()
    terminal_reason: str


class RetrievalObservation(FrozenModel):
    name: str | None = None
    query_hash: str
    source_ids: tuple[str, ...] = ()
    duration_ms: int = Field(default=0, ge=0)


class OutcomeObservation(FrozenModel):
    collector: str
    version: str
    state: JsonValue


class Usage(FrozenModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    tool_calls: int = Field(default=0, ge=0)


class TargetResult(FrozenModel):
    output: JsonValue
    trajectory: tuple[TrajectoryEvent, ...] = ()
    transcript_truncated: bool = False
    loop: LoopObservation | None = None
    retrievals: tuple[RetrievalObservation, ...] = ()
    outcomes: tuple[OutcomeObservation, ...] = ()
    usage: Usage = Field(default_factory=Usage)
    trace_id: str | None = None
    trace_url: str | None = None


class Grade(FrozenModel):
    grader: str
    version: str
    passed: bool
    score: float = Field(ge=0, le=1)
    reason: str
    evidence: dict[str, JsonValue] = Field(default_factory=dict)
    cost_usd: float = Field(default=0, ge=0)


class GraderPolicy(FrozenModel):
    weights: dict[str, float] = Field(default_factory=dict)
    required: frozenset[str] = Field(default_factory=frozenset)
    pass_threshold: float = Field(default=1.0, ge=0, le=1)


class Provenance(FrozenModel):
    harness_version: str
    code_revision: str
    dataset_hash: str
    target_hash: str
    evaluation_suite_id: str = "default"
    evaluation_suite_version: str = "1.0.0"
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    grader_versions: dict[str, str] = Field(default_factory=dict)
    model: str | None = None
    parameters_hash: str | None = None


class TrialRecord(FrozenModel):
    schema_version: str = "1.0"
    run_id: str
    trial_id: str
    case_id: str
    repetition_index: int = Field(default=0, ge=0)
    suite: SuiteType = SuiteType.CAPABILITY
    started_at: datetime
    duration_ms: int = Field(ge=0)
    status: TrialStatus
    input_hash: str
    result: TargetResult | None = None
    grades: tuple[Grade, ...] = ()
    tracked_metrics: frozenset[str] = Field(default_factory=frozenset)
    metrics: dict[str, float] = Field(default_factory=dict)
    score: float = Field(default=0, ge=0, le=1)
    error_type: str | None = None
    error_message: str | None = None
    sandbox: SandboxSession | None = None
    sandbox_cleanup: SandboxCleanup = Field(default_factory=SandboxCleanup)
    provenance: Provenance


class SuiteSummary(FrozenModel):
    trials: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    average_score: float = Field(ge=0, le=1)


class RunSummary(FrozenModel):
    schema_version: str = "1.0"
    run_id: str
    evaluation_suite_id: str = "default"
    evaluation_suite_version: str = "1.0.0"
    started_at: datetime
    finished_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total: int = Field(ge=0)
    cases: int = Field(default=0, ge=0)
    repetitions: int = Field(default=1, ge=1)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    errors: int = Field(ge=0)
    timeouts: int = Field(ge=0)
    pass_rate: float = Field(ge=0, le=1)
    average_score: float = Field(default=0, ge=0, le=1)
    pass_at_k: float = Field(default=0, ge=0, le=1)
    pass_power_k: float = Field(default=0, ge=0, le=1)
    judge_cost_usd: float = Field(default=0, ge=0)
    suites: dict[SuiteType, SuiteSummary] = Field(default_factory=dict)
    export_errors: tuple[str, ...] = ()
    artifact_path: str
