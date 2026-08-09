"""Declarative, deterministic rubric grading.

Rubrics deliberately use small observable assertions.  They are reproducible and
can be re-run from an artifact; subjective criteria should use a model judge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from glyph.core.domain_models import EvalCase, Grade, TargetResult


def _value(document: dict[str, Any], path: str) -> Any:
    current: Any = document
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(path)
        current = current[part]
    return current


@dataclass(frozen=True, slots=True)
class RubricCriterionGrader:
    """One named, weighted criterion from an evaluation spec."""

    criterion_id: str
    description: str
    assertion: str
    output_path: str = "answer"
    expected_path: str | None = None
    expected: Any = None
    case_sensitive: bool = False
    name: str = ""
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if self.assertion not in {"equals", "contains", "exists", "tool_allowed"}:
            raise ValueError(f"Unsupported rubric assertion: {self.assertion}")
        if self.expected_path is not None and self.expected is not None:
            raise ValueError("A rubric criterion may use expected_path or expected, not both")
        if self.name == "":
            object.__setattr__(self, "name", f"rubric.{self.criterion_id}")

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        expected = (
            _value(case.expected, self.expected_path) if self.expected_path else self.expected
        )
        if self.assertion == "tool_allowed":
            allowed = {str(value) for value in (expected or [])}
            used = [
                event.name
                for event in result.trajectory
                if event.kind == "tool_start" and event.name
            ]
            forbidden = sorted(set(used) - allowed)
            passed, score, evidence = (
                not forbidden,
                1.0 if not forbidden else 0.0,
                {"used": used, "forbidden": forbidden},
            )
        else:
            try:
                actual = _value(result.output, self.output_path)
            except KeyError:
                actual = None
            if self.assertion == "exists":
                passed = actual is not None
                score = 1.0 if passed else 0.0
            elif self.assertion == "equals":
                passed = actual == expected
                score = 1.0 if passed else 0.0
            else:
                actual_text = str(actual)
                values = expected if isinstance(expected, list) else [expected]
                missing = [
                    str(item)
                    for item in values
                    if (str(item) if self.case_sensitive else str(item).casefold())
                    not in (actual_text if self.case_sensitive else actual_text.casefold())
                ]
                passed = not missing
                score = (len(values) - len(missing)) / len(values) if values else 1.0
            evidence = {"output_path": self.output_path, "expected": expected, "actual": actual}
            if self.assertion == "contains":
                evidence["missing"] = missing
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=score,
            reason=self.description if passed else f"Rubric criterion failed: {self.description}",
            evidence=evidence,
        )
