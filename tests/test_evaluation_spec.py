from __future__ import annotations

from pathlib import Path

import pytest

from glyph.core.domain_models import EvalCase, TargetResult
from glyph.evaluation.spec import SpecError, load_evaluation_spec
from glyph.grading.rubric import RubricCriterionGrader


@pytest.mark.asyncio
async def test_rubric_criterion_reports_partial_contains_score() -> None:
    grader = RubricCriterionGrader(
        criterion_id="facts",
        description="contains required facts",
        assertion="contains",
        expected_path="contains",
    )
    grade = await grader.grade(
        EvalCase(id="case-1", input={}, expected={"contains": ["one", "two"]}),
        TargetResult(output={"answer": "one"}),
    )
    assert grade.grader == "rubric.facts"
    assert grade.score == 0.5
    assert not grade.passed
    assert grade.evidence["missing"] == ["two"]


def test_spec_rejects_undeclared_grader(tmp_path: Path) -> None:
    spec = tmp_path / "evaluation.yaml"
    spec.write_text(
        "schema_version: 1\n"
        "suite: {id: test, version: 1.0.0}\n"
        "target: {factory: examples.simple_graph:create_evaluation_target}\n"
        "dataset: cases.jsonl\n"
        "graders:\n"
        "  - type: made_up\n",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="Unknown grader"):
        load_evaluation_spec(spec)
