from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import JsonValue

from langgraph_eval.contracts import RunContext
from langgraph_eval.graders import ExactMatchGrader, OutcomeStateGrader
from langgraph_eval.models import (
    Budget,
    EvalCase,
    EvaluationSuite,
    Grade,
    GraderPolicy,
    SandboxRequirements,
    TargetResult,
    TrialRecord,
)
from langgraph_eval.runner import EvaluationRunner


class Target:
    version = "target@1"

    async def execute(self, case: EvalCase, context: RunContext) -> TargetResult:
        return TargetResult(output={"answer": "done"})


class DatabaseOutcomeCollector:
    name = "database"
    version = "1.0.0"

    async def collect(
        self, case: EvalCase, result: TargetResult, context: RunContext
    ) -> JsonValue:
        return {"state": {"reservation_exists": True}}


class UnexpectedGrader:
    name = "unexpected"
    version = "1.0.0"

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        raise AssertionError("Task-level grader selection was ignored")


@pytest.mark.asyncio
async def test_suite_selects_graders_collects_outcome_and_tracks_metrics(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "suite.jsonl"
    case = EvalCase(
        id="booking",
        input={},
        expected={"state": {"reservation_exists": True}},
        graders=frozenset({"outcome_state"}),
        tracked_metrics=frozenset({"latency", "tokens"}),
    )
    summary = await EvaluationRunner(
        target=Target(),
        graders=[
            OutcomeStateGrader(outcome_collector="database"),
            ExactMatchGrader(),
            UnexpectedGrader(),
        ],
        grader_policy=GraderPolicy(pass_threshold=1.0),
        suite=EvaluationSuite(
            id="booking-quality",
            version="2.0.0",
            default_graders=frozenset({"exact_match"}),
            tracked_metrics=frozenset({"tool_calls"}),
        ),
        outcome_collectors=[DatabaseOutcomeCollector()],
        budget=Budget(),
        artifact_path=artifact,
        sandbox_requirements=SandboxRequirements(required=False),
    ).run([case], run_id="suite-run")

    trial = TrialRecord.model_validate_json(artifact.read_text("utf-8").splitlines()[0])
    assert summary.evaluation_suite_id == "booking-quality"
    assert summary.evaluation_suite_version == "2.0.0"
    assert trial.provenance.evaluation_suite_id == "booking-quality"
    assert [grade.grader for grade in trial.grades] == ["outcome_state"]
    assert trial.result is not None
    assert trial.result.outcomes[0].collector == "database"
    assert trial.tracked_metrics == frozenset({"latency", "tokens"})
    assert set(trial.metrics) == {"latency", "tokens"}
    assert json.loads(trial.model_dump_json())["result"]["outcomes"][0]["state"] == {
        "state": {"reservation_exists": True}
    }


@pytest.mark.asyncio
async def test_unknown_task_metric_fails_before_execution(tmp_path: Path) -> None:
    runner = EvaluationRunner(
        target=Target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=tmp_path / "invalid.jsonl",
    )

    with pytest.raises(ValueError, match="unknown metrics"):
        await runner.run(
            [EvalCase(id="invalid", input={}, tracked_metrics=frozenset({"made_up"}))]
        )