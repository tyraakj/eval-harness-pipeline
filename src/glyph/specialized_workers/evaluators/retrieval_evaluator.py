"""Retrieval quality evaluator for specialized evaluation."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from glyph.specialized_workers.artifact import EvaluationArtifact
from glyph.specialized_workers.base import (
    BaseArtifactWorker,
    BaseSpecializedWorker,
    EvaluationEvidence,
    GraderMode,
    Severity,
    WorkerResult,
    WorkerType,
)


@dataclass
class RetrievalPolicy:
    """Policy configuration for retrieval evaluation."""
    partial_scores: dict[str, float]
    f1_excellent_message_template: str
    f1_acceptable_message_template: str
    require_citations: bool = True
    allow_hallucination: bool = False
    max_latency_ms: int = 5000
    min_relevant_sources: int = 1
    require_source_grounding: bool = True
    deduplicate_sources: bool = True
    f1_excellent_threshold: float = 0.9
    f1_acceptable_threshold: float = 0.7


@dataclass
class RetrievalAnalysis:
    """Analysis of retrieval quality."""
    query_hash: str
    retrieved_source_ids: list[str]
    relevant_source_ids: list[str]
    precision: float
    recall: float
    f1: float
    latency_ms: float
    has_citations: bool
    citations_correct: bool
    used_in_answer: bool
    duplicate_sources: list[str]
    out_of_domain_answer: bool = False


class RetrievalEvaluator(BaseSpecializedWorker):
    """Evaluates retrieval quality and citation correctness."""
    
    def __init__(self, version: str = "1.0.0", policy: RetrievalPolicy | None = None):
        super().__init__(version)
        if policy is None:
            raise ValueError("RetrievalPolicy must be provided")
        self.policy = policy
    
    def _get_worker_type(self) -> WorkerType:
        return WorkerType.RETRIEVAL_QUALITY
    
    def can_evaluate(self, evidence: EvaluationEvidence) -> bool:
        """Can evaluate if there are retrieval events in the evidence."""
        return len(evidence.retrieval_events) > 0
    
    def evaluate(self, evidence: EvaluationEvidence) -> WorkerResult:
        """Evaluate retrieval quality."""
        evaluation_id = str(uuid.uuid4())
        started_at = time.monotonic()
        
        # Analyze each retrieval event
        analyses = []
        for event in evidence.retrieval_events:
            analysis = self._analyze_retrieval_event(event, evidence)
            analyses.append(analysis)
        
        # Aggregate findings
        findings = self._aggregate_findings(analyses, evidence)
        
        # Determine overall score and pass/fail
        score, passed, severity, reason_code, reason_message = self._compute_result(
            analyses, findings
        )
        
        # Generate evidence references
        evidence_refs = [f"retrieval_{i}" for i in range(len(evidence.retrieval_events))]
        
        evaluation_duration_ms = int((time.monotonic() - started_at) * 1000)
        
        return self.create_result(
            evaluation_id=evaluation_id,
            trial_id=evidence.trial_id,
            score=score,
            passed=passed,
            severity=severity,
            reason_code=reason_code,
            reason_message=reason_message,
            grader_mode=GraderMode.DETERMINISTIC,
            confidence=1.0,
            evidence_refs=evidence_refs,
            findings=findings,
            evaluation_duration_ms=evaluation_duration_ms,
        )
    
    def _analyze_retrieval_event(
        self, event: dict[str, Any], evidence: EvaluationEvidence
    ) -> RetrievalAnalysis:
        """Analyze a single retrieval event."""
        query_hash = event.get("query_hash", "unknown")
        retrieved_ids = event.get("source_ids", [])
        
        # Get expected relevant sources from metadata if available
        expected_relevant = evidence.metadata.get("expected_relevant_sources", [])
        
        # Calculate precision and recall
        relevant_retrieved = [id for id in retrieved_ids if id in expected_relevant]
        precision = len(relevant_retrieved) / len(retrieved_ids) if retrieved_ids else 0.0
        recall = len(relevant_retrieved) / len(expected_relevant) if expected_relevant else 1.0
        f1 = (
            2 * (precision * recall) / (precision + recall)
            if (precision + recall) > 0 else 0.0
        )
        
        # Check latency
        latency_ms = event.get("duration_ms", 0)
        
        # Check citations
        has_citations = self._has_citations(evidence.final_output)
        citations_correct = self._check_citations_correct(retrieved_ids, evidence.final_output)
        
        # Check if sources were used in answer
        used_in_answer = self._sources_used_in_answer(retrieved_ids, evidence.final_output)
        
        # Check for duplicate sources
        duplicate_sources = self._find_duplicate_sources(retrieved_ids)
        
        # Check if answer goes outside retrieved evidence
        out_of_domain_answer = self._check_out_of_domain(retrieved_ids, evidence.final_output)
        
        return RetrievalAnalysis(
            query_hash=query_hash,
            retrieved_source_ids=retrieved_ids,
            relevant_source_ids=relevant_retrieved,
            precision=precision,
            recall=recall,
            f1=f1,
            latency_ms=latency_ms,
            has_citations=has_citations,
            citations_correct=citations_correct,
            used_in_answer=used_in_answer,
            duplicate_sources=duplicate_sources,
            out_of_domain_answer=out_of_domain_answer,
        )
    
    def _has_citations(self, output: dict[str, Any]) -> bool:
        """Check if output contains citations."""
        output_text = str(output.get("text", output.get("content", "")))
        # Simple citation detection - look for [1], (source), etc.
        return "[" in output_text or "source" in output_text.lower()
    
    def _check_citations_correct(
        self, retrieved_ids: list[str], output: dict[str, Any]
    ) -> bool:
        """Check if citations reference valid retrieved sources."""
        output_text = str(output.get("text", output.get("content", "")))
        
        # Extract citation markers (simplified)
        import re
        citations = re.findall(r'\[(\d+)\]', output_text)
        
        # Check if citation indices are within range
        for citation in citations:
            idx = int(citation) - 1  # Convert to 0-indexed
            if idx < 0 or idx >= len(retrieved_ids):
                return False
        
        return True
    
    def _sources_used_in_answer(
        self, retrieved_ids: list[str], output: dict[str, Any]
    ) -> bool:
        """Check if retrieved sources were actually used in the answer."""
        output_text = str(output.get("text", output.get("content", ""))).lower()
        
        # Check if any source IDs appear in the output
        for source_id in retrieved_ids:
            if source_id.lower() in output_text:
                return True
        
        return len(retrieved_ids) == 0  # Empty retrieval is considered "used"
    
    def _find_duplicate_sources(self, retrieved_ids: list[str]) -> list[str]:
        """Find duplicate source IDs in retrieval."""
        seen = set()
        duplicates = []
        
        for source_id in retrieved_ids:
            if source_id in seen:
                duplicates.append(source_id)
            seen.add(source_id)
        
        return duplicates
    
    def _check_out_of_domain(
        self, retrieved_ids: list[str], output: dict[str, Any]
    ) -> bool:
        """Check if answer contains information outside retrieved sources."""
        # This is a simplified check - in production would use more sophisticated NLP
        output_text = str(output.get("text", output.get("content", "")))
        
        # If no sources were retrieved but answer is substantial, likely hallucinated
        if not retrieved_ids and len(output_text) > 100:
            return True
        
        return False
    
    def _aggregate_findings(
        self, analyses: list[RetrievalAnalysis], evidence: EvaluationEvidence
    ) -> dict[str, Any]:
        """Aggregate retrieval analysis findings."""
        total_retrievals = len(analyses)
        
        # Calculate average metrics
        avg_precision = sum(a.precision for a in analyses) / total_retrievals if total_retrievals else 0.0
        avg_recall = sum(a.recall for a in analyses) / total_retrievals if total_retrievals else 0.0
        avg_f1 = sum(a.f1 for a in analyses) / total_retrievals if total_retrievals else 0.0
        avg_latency = sum(a.latency_ms for a in analyses) / total_retrievals if total_retrievals else 0.0
        
        # Count issues
        missing_citations = [a.query_hash for a in analyses if not a.has_citations]
        incorrect_citations = [a.query_hash for a in analyses if not a.citations_correct]
        unused_sources = [a.query_hash for a in analyses if not a.used_in_answer]
        duplicate_retrievals = [a.query_hash for a in analyses if a.duplicate_sources]
        out_of_domain = [a.query_hash for a in analyses if a.out_of_domain_answer]
        slow_retrievals = [a.query_hash for a in analyses if a.latency_ms > self.policy.max_latency_ms]
        
        # Check minimum relevant sources
        insufficient_sources = [
            a.query_hash for a in analyses
            if len(a.relevant_source_ids) < self.policy.min_relevant_sources
        ]
        
        return {
            "total_retrieval_events": total_retrievals,
            "all_citations_valid": all(a.citations_correct for a in analyses),
            "total_unique_sources": len(set(s for a in analyses for s in a.retrieved_source_ids)),
            "average_precision": avg_precision,
            "average_recall": avg_recall,
            "average_f1": avg_f1,
            "average_latency_ms": avg_latency,
            "missing_citations": missing_citations,
            "incorrect_citations": incorrect_citations,
            "unused_sources": unused_sources,
            "duplicate_retrievals": duplicate_retrievals,
            "out_of_domain_answers": out_of_domain,
            "slow_retrievals": slow_retrievals,
            "insufficient_sources": insufficient_sources,
            "retrieval_details": [
                {
                    "query_hash": a.query_hash,
                    "precision": a.precision,
                    "recall": a.recall,
                    "f1": a.f1,
                    "latency_ms": a.latency_ms,
                    "has_citations": a.has_citations,
                    "citations_correct": a.citations_correct,
                    "used_in_answer": a.used_in_answer,
                    "duplicate_sources": a.duplicate_sources,
                }
                for a in analyses
            ]
        }
    
    def _compute_result(
        self, analyses: list[RetrievalAnalysis], findings: dict[str, Any]
    ) -> tuple[float, bool, Severity, str, str]:
        """Compute overall score and pass/fail result."""
        # Critical failures
        if findings["out_of_domain_answers"] and not self.policy.allow_hallucination:
            return (
                0.0,
                False,
                Severity.CRITICAL,
                "hallucination_detected",
                f"Answers outside retrieved evidence: {', '.join(findings['out_of_domain_answers'])}"
            )
        
        if findings["total_retrieval_events"] == 0 and self.policy.require_citations:
            return (
                self.policy.partial_scores["no_retrieval"],
                False,
                Severity.CRITICAL,
                "no_retrieval",
                "No retrieval events found but citations are required"
            )
        
        # High severity failures
        if findings["incorrect_citations"]:
            return (
                self.policy.partial_scores.get("incorrect_citations", 0.5),
                False,
                Severity.ERROR,
                "incorrect_citations",
                f"Incorrect citations: {', '.join(findings['incorrect_citations'])}"
            )
        
        if findings["average_latency_ms"] > self.policy.max_latency_ms:
            return (
                self.policy.partial_scores.get("slow_retrieval", 0.6),
                False,
                Severity.ERROR,
                "slow_retrieval",
                f"Average latency {findings['average_latency_ms']:.0f}ms exceeds limit {self.policy.max_latency_ms}ms"
            )
        
        # Medium severity failures
        if not findings["all_citations_valid"] and self.policy.require_citations:
            return (
                self.policy.partial_scores["no_retrieval"],
                False,
                Severity.ERROR,
                "invalid_citations",
                "Some citations do not match retrieved sources"
            )
        
        if findings["total_unique_sources"] < self.policy.min_relevant_sources:
            return (
                self.policy.partial_scores["poor_recall"],
                False,
                Severity.WARNING,
                "insufficient_sources",
                f"Not enough unique sources retrieved: {findings['total_unique_sources']} < {self.policy.min_relevant_sources}"
            )
        
        if findings["missing_citations"] and self.policy.require_citations:
            return (
                self.policy.partial_scores.get("missing_citations", 0.7),
                False,
                Severity.WARNING,
                "missing_citations",
                f"Missing citations: {', '.join(findings['missing_citations'])}"
            )
        
        # Low severity issues
        if findings["duplicate_retrievals"] and self.policy.deduplicate_sources:
            return (
                self.policy.partial_scores.get("duplicate_retrievals", 0.8),
                False,
                Severity.WARNING,
                "duplicate_retrievals",
                f"Duplicate retrievals: {', '.join(findings['duplicate_retrievals'])}"
            )
        
        if findings["unused_sources"] and self.policy.require_source_grounding:
            return (
                self.policy.partial_scores.get("unused_sources", 0.85),
                False,
                Severity.INFO,
                "unused_sources",
                f"Sources not used in answer: {', '.join(findings['unused_sources'])}"
            )
        
        # Score based on F1
        avg_f1 = findings["average_f1"]
        if avg_f1 >= self.policy.f1_excellent_threshold:
            return (
                1.0,
                True,
                Severity.INFO,
                "excellent_retrieval",
                self.policy.f1_excellent_message_template.format(f1=avg_f1)
            )
        elif avg_f1 >= self.policy.f1_acceptable_threshold:
            return (
                avg_f1,
                True,
                Severity.INFO,
                "good_retrieval",
                self.policy.f1_acceptable_message_template.format(f1=avg_f1)
            )
        else:
            return (
                avg_f1,
                False,
                Severity.WARNING,
                "marginal_retrieval",
                f"Retrieval quality is marginal (F1: {avg_f1:.2f})"
            )


class ArtifactRetrievalEvaluator(BaseArtifactWorker, RetrievalEvaluator):
    """Retrieval quality evaluator that works with immutable artifacts."""
    
    def __init__(self, version: str = "1.0.0", policy: RetrievalPolicy | None = None):
        BaseArtifactWorker.__init__(self, version)
        RetrievalEvaluator.__init__(self, version, policy)
    
    def _get_worker_type(self) -> WorkerType:
        return WorkerType.RETRIEVAL_QUALITY
    
    def can_evaluate_artifact(self, artifact: EvaluationArtifact) -> bool:
        """Can evaluate if artifact has retrieval events."""
        retrieval_events = [
            event for event in artifact.events
            if event.get("event_type") == "retrieval"
        ]
        return len(retrieval_events) > 0
    
    def evaluate_artifact(self, artifact: EvaluationArtifact) -> WorkerResult:
        """Evaluate artifact by extracting evidence and delegating to base evaluator."""
        evidence = self.extract_evidence_from_artifact(artifact)
        return self.evaluate(evidence)
