from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import ValidationError

from langgraph_eval.evaluation.human import (
    HumanEvaluationLedger,
    HumanReviewRubric,
    HumanReviewTask,
)
from langgraph_eval.exporters.langsmith_exporter import LangSmithExporter
from langgraph_eval.core.models import (
    EvalCase,
    Grade,
    OnlineEvaluationPolicy,
    Provenance,
    TargetResult,
    TrialRecord,
    TrialStatus,
)


class FakeClient:
    def __init__(self) -> None:
        self.examples: list[dict[str, object]] = []
        self.feedback: list[dict[str, object]] = []
        self.queued: list[str] = []
        self.projects: list[tuple[str, dict[str, object]]] = []
        self.runs: list[dict[str, object]] = []
        self.human_feedback: list[SimpleNamespace] = []

    def read_dataset(self, *, dataset_name: str) -> SimpleNamespace:
        return SimpleNamespace(id=f"dataset:{dataset_name}")

    def create_example(self, **kwargs: object) -> SimpleNamespace:
        self.examples.append(kwargs)
        return SimpleNamespace(id="example-1")

    def read_example(self, example_id: UUID) -> SimpleNamespace:
        raise type("LangSmithNotFoundError", (Exception,), {})()

    def update_example(self, example_id: UUID, **kwargs: object) -> None:
        self.examples.append(kwargs)

    def create_feedback(self, **kwargs: object) -> None:
        self.feedback.append(kwargs)

    def create_project(self, project_name: str, **kwargs: object) -> SimpleNamespace:
        self.projects.append((project_name, kwargs))
        return SimpleNamespace(id="project-1")

    def create_run(self, **kwargs: object) -> None:
        self.runs.append(kwargs)

    def add_runs_to_annotation_queue(
        self, queue_id: str, *, run_ids: list[str]
    ) -> None:
        self.queued.extend(f"{queue_id}:{run_id}" for run_id in run_ids)

    def list_feedback(
        self, *, run_ids: list[str], feedback_key: list[str]
    ) -> list[SimpleNamespace]:
        assert run_ids == ["trace-1"]
        assert feedback_key == ["human.correctness"]
        return self.human_feedback


def trial_record() -> TrialRecord:
    return TrialRecord(
        run_id="run",
        trial_id="trial",
        case_id="case",
        started_at=datetime.now(UTC),
        duration_ms=1,
        status=TrialStatus.FAILED,
        input_hash="sha256:test",
        result=TargetResult(output={}, trace_id="trace-1"),
        grades=(
            Grade(
                grader="quality",
                version="1",
                passed=False,
                score=0.2,
                reason="incorrect",
            ),
        ),
        provenance=Provenance(
            harness_version="1",
            code_revision="test",
            dataset_hash="sha256:dataset",
            target_hash="sha256:target",
        ),
    )


@pytest.mark.asyncio
async def test_langsmith_exporter_mirrors_feedback_and_annotation() -> None:
    client = FakeClient()
    exporter = LangSmithExporter(
        dataset_name="evals", client=client, annotation_queue_id="review"
    )
    await exporter.export_trial(
        EvalCase(id="case", input={"secret": "safe"}),
        trial_record(),
        idempotency_key="trial-key",
    )

    assert len(client.examples) == 1
    assert client.projects[0][0] == "local-evaluation-run"
    assert client.runs[0]["project_name"] == "local-evaluation-run"
    assert client.runs[0]["reference_example_id"]
    assert isinstance(client.feedback[0]["run_id"], UUID)
    assert client.feedback[0]["key"] == "eval.quality"
    assert client.queued == ["review:trace-1"]


@pytest.mark.asyncio
async def test_trace_promotion_uses_source_run_io() -> None:
    client = FakeClient()
    exporter = LangSmithExporter(dataset_name="evals", client=client)
    example_id = await exporter.promote_trace_to_dataset("trace-1")

    assert example_id == "example-1"
    assert client.examples[0]["source_run_id"] == "trace-1"
    assert client.examples[0]["use_source_run_io"] is True


@pytest.mark.asyncio
async def test_completed_annotations_import_into_canonical_human_ledger(tmp_path: object) -> None:
    assert isinstance(tmp_path, Path)
    client = FakeClient()
    client.human_feedback.append(
        SimpleNamespace(
            id="feedback-1",
            value="pass",
            score=0.95,
            comment="The observable outcome satisfies the task.",
            source_info={
                "reviewer_pseudonym": "reviewer-a",
                "rubric_version": "1.0",
                "confidence": 0.9,
                "evidence": {"checked": "outcome"},
            },
            created_at=datetime.now(UTC),
        )
    )
    ledger = HumanEvaluationLedger(tmp_path / "human-reviews.jsonl")
    await ledger.initialize()
    await ledger.create_task(
        HumanReviewTask(
            task_id="human-task",
            trial_id="trial",
            case_id="case",
            trace_id="trace-1",
            rubric=HumanReviewRubric(
                id="correctness",
                version="1.0",
                dimension="Correctness",
                instructions="Assess the observable outcome.",
            ),
        )
    )
    exporter = LangSmithExporter(dataset_name="evals", client=client)

    assert await exporter.import_human_reviews(
        trace_id="trace-1", task_id="human-task", ledger=ledger
    ) == 1
    assert await exporter.import_human_reviews(
        trace_id="trace-1", task_id="human-task", ledger=ledger
    ) == 0
    assert ledger.active_grades("human-task")[0].source_id == "feedback-1"


def test_online_evaluation_requires_all_production_controls() -> None:
    with pytest.raises(ValidationError, match="privacy_review_id"):
        OnlineEvaluationPolicy(enabled=True, sampling_rate=0.1)

    policy = OnlineEvaluationPolicy(
        enabled=True,
        privacy_review_id="privacy-42",
        sampling_rate=0.05,
        retention_days=30,
        maximum_monthly_cost_usd=50,
        allowed_project="production-evals",
    )
    assert policy.enabled