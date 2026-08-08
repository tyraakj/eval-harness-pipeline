"""Base models and interfaces for specialized evaluation workers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from glyph.specialized_workers.artifact import EvaluationArtifact


class WorkerType(StrEnum):
    """Types of specialized evaluation workers."""
    TOOL_POLICY = "tool_policy"
    RETRIEVAL_QUALITY = "retrieval_quality"
    GRAPH_COMPLIANCE = "graph_compliance"
    OUTPUT_QUALITY = "output_quality"
    SECURITY = "security"
    PERFORMANCE = "performance"


class GraderMode(StrEnum):
    """Mode used for grading."""
    DETERMINISTIC = "deterministic"
    MODEL_JUDGE = "model_judge"
    HYBRID = "hybrid"


class Severity(StrEnum):
    """Severity levels for evaluation findings."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class EvaluationEvidence:
    """Bounded evidence collected during trial execution."""
    trial_id: str
    run_id: str
    case_id: str
    
    # Tool execution evidence
    tool_calls: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    tool_errors: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    
    # Retrieval evidence
    retrieval_events: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    source_ids: tuple[str, ...] = field(default_factory=tuple)
    
    # Graph execution evidence
    graph_nodes: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    graph_edges: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    state_transitions: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    
    # Output evidence
    final_output: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    
    # Security evidence
    security_events: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    auth_attempts: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    
    # Performance evidence
    latency_ms: float = 0.0
    token_usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0
    timestamps: dict[str, datetime] = field(default_factory=dict)
    
    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def get_evidence_refs(self) -> list[str]:
        """Generate evidence reference IDs for traceability."""
        refs = []
        
        for i, call in enumerate(self.tool_calls):
            refs.append(f"tool_call_{i}")
        
        for i, event in enumerate(self.retrieval_events):
            refs.append(f"retrieval_{i}")
        
        for i, node in enumerate(self.graph_nodes):
            refs.append(f"node_{node.get('node_id', i)}")
        
        for i, event in enumerate(self.security_events):
            refs.append(f"security_{i}")
        
        return refs


class WorkerResult(BaseModel):
    """Versioned, structured result from a specialized worker."""
    evaluation_id: str = Field(min_length=1)
    worker_type: WorkerType
    worker_version: str = Field(min_length=1)
    trial_id: str = Field(min_length=1)
    
    # Scoring
    score: float = Field(ge=0.0, le=1.0)
    passed: bool
    severity: Severity = Severity.INFO
    
    # Diagnostic information
    reason_code: str = Field(min_length=1)
    reason_message: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    
    # Grading metadata
    grader_mode: GraderMode = GraderMode.DETERMINISTIC
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    
    # Additional findings
    findings: dict[str, Any] = Field(default_factory=dict)
    
    # Timing
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    evaluation_duration_ms: int = Field(default=0, ge=0)
    
    # Model judge metadata (if applicable)
    judge_model: str | None = None
    judge_prompt_version: str | None = None
    judge_cost_usd: float = Field(default=0.0, ge=0.0)
    judge_latency_ms: int = Field(default=0, ge=0)
    
    class Config:
        use_enum_values = True


class BaseSpecializedWorker(ABC):
    """Base class for specialized evaluation workers."""
    
    def __init__(self, version: str = "1.0.0"):
        self.version = version
        self.worker_type = self._get_worker_type()
    
    @abstractmethod
    def _get_worker_type(self) -> WorkerType:
        """Return the worker type for this specialized evaluator."""
        pass
    
    @abstractmethod
    def can_evaluate(self, evidence: EvaluationEvidence) -> bool:
        """Determine if this worker can evaluate the given evidence."""
        pass
    
    @abstractmethod
    def evaluate(self, evidence: EvaluationEvidence) -> WorkerResult:
        """Evaluate the evidence and return a structured result."""
        pass
        
    def create_result(
        self,
        evaluation_id: str,
        trial_id: str,
        score: float,
        passed: bool,
        reason_code: str,
        reason_message: str,
        severity: Severity = Severity.INFO,
        grader_mode: GraderMode = GraderMode.DETERMINISTIC,
        confidence: float = 1.0,
        evidence_refs: list[str] | None = None,
        findings: dict[str, Any] | None = None,
        **kwargs
    ) -> WorkerResult:
        """Helper method to create a WorkerResult with common fields."""
        return WorkerResult(
            evaluation_id=evaluation_id,
            worker_type=self.worker_type,
            worker_version=self.version,
            trial_id=trial_id,
            score=score,
            passed=passed,
            severity=severity,
            reason_code=reason_code,
            reason_message=reason_message,
            evidence_refs=evidence_refs or [],
            grader_mode=grader_mode,
            confidence=confidence,
            findings=findings or {},
            **kwargs
        )


class BaseArtifactWorker(ABC):
    """Base class for workers that process immutable artifacts for replay."""
    
    def __init__(self, version: str = "1.0.0"):
        self.version = version
        self.worker_type = self._get_worker_type()
    
    @abstractmethod
    def _get_worker_type(self) -> WorkerType:
        """Return the worker type for this specialized evaluator."""
        pass
    
    @abstractmethod
    def can_evaluate_artifact(self, artifact: EvaluationArtifact) -> bool:
        """Determine if this worker can evaluate the given artifact."""
        pass
    
    @abstractmethod
    def evaluate_artifact(self, artifact: EvaluationArtifact) -> WorkerResult:
        """Evaluate the artifact and return a structured result."""
        pass
    
    def extract_evidence_from_artifact(
        self, artifact: EvaluationArtifact
    ) -> EvaluationEvidence:
        """Extract EvaluationEvidence from an EvaluationArtifact."""
        return EvaluationEvidence(
            trial_id=artifact.trial_id,
            run_id=artifact.run_id,
            case_id=artifact.case_id,
            tool_calls=tuple(
                event for event in artifact.events
                if event.get("event_type") == "tool_call"
            ),
            tool_errors=tuple(
                event for event in artifact.events
                if event.get("event_type") == "tool_error"
            ),
            retrieval_events=tuple(
                event for event in artifact.events
                if event.get("event_type") == "retrieval"
            ),
            graph_nodes=tuple(
                event for event in artifact.events
                if event.get("event_type") == "graph_node"
            ),
            graph_edges=tuple(
                event for event in artifact.events
                if event.get("event_type") == "graph_edge"
            ),
            final_output=artifact.final_output,
            security_events=tuple(
                event for event in artifact.events
                if event.get("event_type") == "security"
            ),
            token_usage={
                "input_tokens": artifact.usage.input_tokens,
                "output_tokens": artifact.usage.output_tokens,
            },
            cost_usd=artifact.usage.estimated_cost,
            metadata={
                "artifact_id": artifact.artifact_id,
                "mode": artifact.mode.value,
                "target_version": artifact.target_version,
            },
        )
    
    def create_result(
        self,
        evaluation_id: str,
        trial_id: str,
        score: float,
        passed: bool,
        reason_code: str,
        reason_message: str,
        severity: Severity = Severity.INFO,
        grader_mode: GraderMode = GraderMode.DETERMINISTIC,
        confidence: float = 1.0,
        evidence_refs: list[str] | None = None,
        findings: dict[str, Any] | None = None,
        **kwargs
    ) -> WorkerResult:
        """Helper method to create a WorkerResult with common fields."""
        return WorkerResult(
            evaluation_id=evaluation_id,
            worker_type=self.worker_type,
            worker_version=self.version,
            trial_id=trial_id,
            score=score,
            passed=passed,
            severity=severity,
            reason_code=reason_code,
            reason_message=reason_message,
            evidence_refs=evidence_refs or [],
            grader_mode=grader_mode,
            confidence=confidence,
            findings=findings or {},
            **kwargs
        )
    
    def get_idempotency_key(self, trial_id: str) -> str:
        """Generate idempotency key for this worker evaluation."""
        return f"{trial_id}_{self.worker_type}_{self.version}"
