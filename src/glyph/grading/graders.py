from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pydantic import JsonValue

from glyph.core.models import EvalCase, Grade, RetrievalExpectation, TargetResult


def _path(value: Any, dotted_path: str) -> Any:
    current = value
    for part in dotted_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(dotted_path)
    return current


@dataclass(frozen=True, slots=True)
class ExactMatchGrader:
    output_path: str = "answer"
    expected_path: str = "answer"
    name: str = "exact_match"
    version: str = "1.0.0"

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        actual = _path(result.output, self.output_path)
        expected = _path(case.expected, self.expected_path)
        passed = actual == expected
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=1.0 if passed else 0.0,
            reason="Values match" if passed else "Actual value differs from expected value",
            evidence={"output_path": self.output_path, "expected_path": self.expected_path},
        )


@dataclass(frozen=True, slots=True)
class ContainsAllGrader:
    output_path: str = "answer"
    expected_path: str = "contains"
    case_sensitive: bool = False
    name: str = "contains_all"
    version: str = "1.0.0"

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        actual = str(_path(result.output, self.output_path))
        expected = [str(item) for item in _path(case.expected, self.expected_path)]
        haystack = actual if self.case_sensitive else actual.casefold()
        missing = [
            item
            for item in expected
            if (item if self.case_sensitive else item.casefold()) not in haystack
        ]
        score = (len(expected) - len(missing)) / len(expected) if expected else 1.0
        return Grade(
            grader=self.name,
            version=self.version,
            passed=not missing,
            score=score,
            reason=(
                "All required values are present" if not missing else "Required values are missing"
            ),
            evidence={"missing": cast(JsonValue, missing)},
        )


@dataclass(frozen=True, slots=True)
class ToolPolicyGrader:
    allowed_tools: frozenset[str]
    name: str = "tool_policy"
    version: str = "1.0.0"

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        used = [
            event.name
            for event in result.trajectory
            if event.kind == "tool_start" and event.name
        ]
        forbidden = sorted(set(used) - self.allowed_tools)
        return Grade(
            grader=self.name,
            version=self.version,
            passed=not forbidden,
            score=1.0 if not forbidden else 0.0,
            reason="Tool policy satisfied" if not forbidden else "Forbidden tools were invoked",
            evidence={
                "used": cast(JsonValue, used),
                "forbidden": cast(JsonValue, forbidden),
            },
        )


@dataclass(frozen=True, slots=True)
class OutcomeStateGrader:
    output_path: str = "state"
    expected_path: str = "state"
    outcome_collector: str | None = None
    name: str = "outcome_state"
    version: str = "1.0.0"

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        source = result.output
        if self.outcome_collector is not None:
            observation = next(
                (
                    outcome
                    for outcome in result.outcomes
                    if outcome.collector == self.outcome_collector
                ),
                None,
            )
            if observation is None:
                raise ValueError(
                    f"Missing outcome from collector {self.outcome_collector!r}"
                )
            source = observation.state
        actual = _path(source, self.output_path) if self.output_path else source
        expected = _path(case.expected, self.expected_path)
        if not isinstance(actual, dict) or not isinstance(expected, dict):
            raise TypeError("Outcome state values must be mappings")
        matched = sorted(key for key, value in expected.items() if actual.get(key) == value)
        missing = sorted(key for key in expected if key not in matched)
        score = len(matched) / len(expected) if expected else 1.0
        return Grade(
            grader=self.name,
            version=self.version,
            passed=not missing,
            score=score,
            reason="Expected state reached" if not missing else "Expected state differs",
            evidence={
                "collector": self.outcome_collector,
                "matched": cast(JsonValue, matched),
                "missing": cast(JsonValue, missing),
            },
        )


@dataclass(frozen=True, slots=True)
class TrajectorySubsequenceGrader:
    expected: tuple[str, ...]
    name: str = "trajectory_subsequence"
    version: str = "1.0.0"

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        observed = tuple(
            f"{event.kind}:{event.name}" if event.name else event.kind
            for event in result.trajectory
        )
        matched = 0
        for event in observed:
            if matched < len(self.expected) and event == self.expected[matched]:
                matched += 1
        score = matched / len(self.expected) if self.expected else 1.0
        passed = matched == len(self.expected)
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=score,
            reason=(
                "Required trajectory subsequence observed"
                if passed
                else "Required trajectory subsequence was incomplete"
            ),
            evidence={
                "expected": cast(JsonValue, list(self.expected)),
                "observed": cast(JsonValue, list(observed)),
                "matched": matched,
            },
        )


@dataclass(frozen=True, slots=True)
class LoopEfficiencyGrader:
    max_iterations: int
    max_consecutive_same_node: int = 3
    allowed_terminal_reasons: frozenset[str] = frozenset({"completed"})
    name: str = "loop_efficiency"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.max_iterations < 1 or self.max_consecutive_same_node < 1:
            raise ValueError("Loop limits must be at least one")

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        if result.loop is None:
            raise ValueError("Target did not provide a loop observation")
        nodes = [iteration.node for iteration in result.loop.iterations]
        longest_run = 0
        current_run = 0
        previous = None
        for node in nodes:
            current_run = current_run + 1 if node == previous else 1
            longest_run = max(longest_run, current_run)
            previous = node
        iteration_ratio = min(1.0, len(nodes) / self.max_iterations)
        passed = (
            len(nodes) <= self.max_iterations
            and longest_run <= self.max_consecutive_same_node
            and result.loop.terminal_reason in self.allowed_terminal_reasons
        )
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=1.0 if passed else max(0.0, 1.0 - iteration_ratio),
            reason="Loop policy satisfied" if passed else "Loop policy was exceeded",
            evidence={
                "iterations": len(nodes),
                "longest_consecutive_node_run": longest_run,
                "terminal_reason": result.loop.terminal_reason,
            },
        )


@dataclass(frozen=True, slots=True)
class RetrievalMetricsGrader:
    k: int = 5
    expected_path: str = "relevant_source_ids"
    minimum_recall: float = 1.0
    minimum_precision: float = 0.0
    minimum_mrr: float = 0.0
    minimum_ndcg: float = 0.0
    name: str = "retrieval_metrics"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError("k must be at least one")
        for threshold in (self.minimum_recall, self.minimum_precision, self.minimum_mrr, self.minimum_ndcg):
            if not 0 <= threshold <= 1:
                raise ValueError("Retrieval metric thresholds must be between zero and one")

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        if self.expected_path == "relevant_source_ids":
            expectation = RetrievalExpectation.model_validate(
                {"relevant_source_ids": case.expected.get("relevant_source_ids")}
            )
            relevant = set(expectation.relevant_source_ids)
        else:
            relevant = {str(value) for value in _path(case.expected, self.expected_path)}
        retrieved = [
            source_id
            for observation in result.retrievals
            for source_id in observation.source_ids
        ]
        if not retrieved:
            for event in result.trajectory:
                if event.kind == "retrieval":
                    source_ids = event.data.get("source_ids", [])
                    if not isinstance(source_ids, list):
                        raise TypeError("Retrieval source_ids must be a list")
                    retrieved.extend(str(value) for value in source_ids)
        if len(retrieved) != len(set(retrieved)):
            raise ValueError("Retrieved source IDs must be unique and ranked")
        top_k = retrieved[: self.k]
        relevant_retrieved = [source_id for source_id in top_k if source_id in relevant]
        recall = len(set(relevant_retrieved)) / len(relevant) if relevant else 1.0
        precision = len(relevant_retrieved) / len(top_k) if top_k else 0.0
        reciprocal_rank = next(
            (1 / rank for rank, source_id in enumerate(top_k, start=1) if source_id in relevant),
            0.0,
        )
        
        # Calculate nDCG
        dcg = 0.0
        for rank, source_id in enumerate(top_k, start=1):
            if source_id in relevant:
                dcg += 1.0 / (rank + 1)  # log2(rank+1) simplified to rank+1 for binary relevance
        # Ideal DCG: all relevant items at top positions
        idcg = sum(1.0 / (i + 1) for i in range(min(len(relevant), self.k)))
        ndcg = dcg / idcg if idcg > 0 else 0.0
        
        passed = (
            recall >= self.minimum_recall
            and precision >= self.minimum_precision
            and reciprocal_rank >= self.minimum_mrr
            and ndcg >= self.minimum_ndcg
        )
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=(recall + precision + reciprocal_rank + ndcg) / 4,
            reason="Retrieval thresholds satisfied" if passed else "Retrieval thresholds not met",
            evidence={
                "k": self.k,
                "recall_at_k": recall,
                "precision_at_k": precision,
                "mrr": reciprocal_rank,
                "ndcg": ndcg,
                "retrieved_source_ids": cast(JsonValue, top_k),
            },
        )


@dataclass(frozen=True, slots=True)
class DuplicateRateGrader:
    """Grader that penalizes duplicate documents in retrieval results."""
    output_path: str = "retrieved_documents"
    maximum_duplicate_rate: float = 0.0
    name: str = "duplicate_rate"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not 0 <= self.maximum_duplicate_rate <= 1:
            raise ValueError("Maximum duplicate rate must be between zero and one")

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        retrieved = _path(result.output, self.output_path)
        if not isinstance(retrieved, list):
            raise TypeError("Retrieved documents must be a list")
        
        # Check for duplicates by document ID or content hash
        seen = set()
        duplicates = 0
        for doc in retrieved:
            if isinstance(doc, dict):
                doc_key = doc.get("id") or doc.get("content_hash") or str(doc)
            else:
                doc_key = str(doc)
            
            if doc_key in seen:
                duplicates += 1
            else:
                seen.add(doc_key)
        
        duplicate_rate = duplicates / len(retrieved) if retrieved else 0.0
        passed = duplicate_rate <= self.maximum_duplicate_rate
        score = 1.0 - duplicate_rate
        
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=score,
            reason="Duplicate rate within threshold" if passed else "Too many duplicates",
            evidence={
                "duplicate_rate": duplicate_rate,
                "duplicates": duplicates,
                "total_retrieved": len(retrieved),
            },
        )


@dataclass(frozen=True, slots=True)
class ContextCoverageGrader:
    """Grader that measures how well retrieved context covers the query's information needs."""
    output_path: str = "retrieved_context"
    expected_path: str = "required_concepts"
    minimum_coverage: float = 0.8
    name: str = "context_coverage"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_coverage <= 1:
            raise ValueError("Minimum coverage must be between zero and one")

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        required_concepts = set(_path(case.expected, self.expected_path))
        if not isinstance(required_concepts, set):
            required_concepts = {str(item) for item in required_concepts}
        
        retrieved_context = str(_path(result.output, self.output_path)).lower()
        
        # Check which required concepts are mentioned in the retrieved context
        covered_concepts = {
            concept for concept in required_concepts
            if concept.lower() in retrieved_context
        }
        
        coverage = len(covered_concepts) / len(required_concepts) if required_concepts else 1.0
        passed = coverage >= self.minimum_coverage
        
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=coverage,
            reason="Context coverage sufficient" if passed else "Context coverage insufficient",
            evidence={
                "coverage": coverage,
                "covered_concepts": cast(JsonValue, sorted(covered_concepts)),
                "missing_concepts": cast(JsonValue, sorted(required_concepts - covered_concepts)),
            },
        )


@dataclass(frozen=True, slots=True)
class RerankingLatencyGrader:
    """Grader that measures reranking operation latency."""
    output_path: str = "reranking_latency_ms"
    maximum_latency_ms: float = 1000.0
    name: str = "reranking_latency"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.maximum_latency_ms < 0:
            raise ValueError("Maximum latency must be non-negative")

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        latency = _path(result.output, self.output_path)
        if not isinstance(latency, (int, float)):
            raise TypeError("Reranking latency must be a number")
        
        passed = latency <= self.maximum_latency_ms
        # Score degrades linearly as latency increases beyond threshold
        score = 1.0 if passed else max(0.0, 1.0 - (latency - self.maximum_latency_ms) / self.maximum_latency_ms)
        
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=score,
            reason="Reranking latency acceptable" if passed else "Reranking latency too high",
            evidence={
                "latency_ms": latency,
                "maximum_latency_ms": self.maximum_latency_ms,
            },
        )
