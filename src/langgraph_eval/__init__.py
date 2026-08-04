"""LangGraph-native evaluation harness."""

from __future__ import annotations

from langgraph_eval.core.models import (
    Budget,
    EvalCase,
    EvaluationSuite,
    ExportPolicy,
    Grade,
    GraderPolicy,
    LoopIteration,
    LoopObservation,
    OnlineEvaluationDecision,
    OnlineEvaluationPolicy,
    OnlineEvaluationStatus,
    OutcomeObservation,
    ReleaseDecision,
    ReleasePolicy,
    RetrievalExpectation,
    RetrievalObservation,
    RunSummary,
    SandboxCleanup,
    SandboxRequirements,
    SandboxSession,
    SecurityDecision,
    SecurityExpectation,
    SuiteSummary,
    SuiteType,
    TargetResult,
    TranscriptCapturePolicy,
    TrialRecord,
    TrialStatus,
)

try:
    from langgraph_eval.evaluation.human import (
        HumanAdjudication,
        HumanEvaluationLedger,
        HumanGrade,
        HumanGrader,
        HumanReleaseDecision,
        HumanReleasePolicy,
        HumanReviewAssignment,
        HumanReviewDecision,
        HumanReviewPolicy,
        HumanReviewRubric,
        HumanReviewStatus,
        HumanReviewSummary,
        HumanReviewTask,
    )
    from langgraph_eval.evaluation.optimizers import (
        OptimizationCandidate,
        OptimizationResult,
        Optimizer,
    )
    from langgraph_eval.evaluation.release_gate import ReleaseGate
    _HUMAN_AVAILABLE = True
except ImportError:
    _HUMAN_AVAILABLE = False

try:
    from langgraph_eval.monitoring.observability import (
        OtelRuntime,
        configure_otel,
        configure_otel_from_env,
    )
    _OBSERVABILITY_AVAILABLE = True
except ImportError:
    _OBSERVABILITY_AVAILABLE = False

__all__ = [
    "Budget",
    "EvalCase",
    "EvaluationSuite",
    "ExportPolicy",
    "Grade",
    "GraderPolicy",
    "LoopIteration",
    "LoopObservation",
    "OnlineEvaluationDecision",
    "OnlineEvaluationPolicy",
    "OnlineEvaluationStatus",
    "OutcomeObservation",
    "ReleaseDecision",
    "ReleasePolicy",
    "RetrievalExpectation",
    "RetrievalObservation",
    "RunSummary",
    "SandboxCleanup",
    "SandboxRequirements",
    "SandboxSession",
    "SecurityDecision",
    "SecurityExpectation",
    "SuiteSummary",
    "SuiteType",
    "TargetResult",
    "TranscriptCapturePolicy",
    "TrialRecord",
    "TrialStatus",
]

if _HUMAN_AVAILABLE:
    __all__.extend([
        "HumanAdjudication",
        "HumanEvaluationLedger",
        "HumanGrade",
        "HumanGrader",
        "HumanReleaseDecision",
        "HumanReleasePolicy",
        "HumanReviewAssignment",
        "HumanReviewDecision",
        "HumanReviewPolicy",
        "HumanReviewRubric",
        "HumanReviewStatus",
        "HumanReviewSummary",
        "HumanReviewTask",
        "OptimizationCandidate",
        "OptimizationResult",
        "Optimizer",
        "ReleaseGate",
    ])

if _OBSERVABILITY_AVAILABLE:
    __all__.extend([
        "OtelRuntime",
        "configure_otel",
        "configure_otel_from_env",
    ])
