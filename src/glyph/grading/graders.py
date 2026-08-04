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
    name: str = "retrieval_metrics"
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.k < 1:
            raise ValueError("k must be at least one")
        for threshold in (self.minimum_recall, self.minimum_precision, self.minimum_mrr):
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
        passed = (
            recall >= self.minimum_recall
            and precision >= self.minimum_precision
            and reciprocal_rank >= self.minimum_mrr
        )
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=(recall + precision + reciprocal_rank) / 3,
            reason="Retrieval thresholds satisfied" if passed else "Retrieval thresholds not met",
            evidence={
                "k": self.k,
                "recall_at_k": recall,
                "precision_at_k": precision,
                "mrr": reciprocal_rank,
                "retrieved_source_ids": cast(JsonValue, top_k),
            },
        )
