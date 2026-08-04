from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from langgraph_eval.security.contracts import RunContext
from langgraph_eval.grading.graders import ExactMatchGrader
from langgraph_eval.targets.langgraph_target import LangGraphTarget
from langgraph_eval.core.models import (
    Budget,
    EvalCase,
    SandboxRequirements,
    SandboxSession,
    TrialRecord,
    TrialStatus,
)
from langgraph_eval.evaluation.runner import EvaluationRunner


class State(TypedDict, total=False):
    value: str
    answer: str


def graph_target() -> LangGraphTarget:
    builder = StateGraph(State)
    builder.add_node("answer", lambda state: {"answer": state["value"].upper()})
    builder.add_edge(START, "answer")
    builder.add_edge("answer", END)
    return LangGraphTarget(builder.compile(), version="test@1")


class RecordingSandboxProvider:
    name = "recording"
    capabilities = frozenset({"process", "filesystem"})

    def __init__(self, *, fail_cleanup: bool = False) -> None:
        self.fail_cleanup = fail_cleanup
        self.provisioned: list[str] = []
        self.destroyed: list[str] = []

    async def provision(self, case: EvalCase, context: RunContext) -> SandboxSession:
        self.provisioned.append(context.trial_id)
        return SandboxSession(
            id=context.trial_id, provider=self.name, isolation="test-process"
        )

    async def reset(self, session: SandboxSession) -> None:
        return None

    async def destroy(self, session: SandboxSession) -> None:
        self.destroyed.append(session.id)
        if self.fail_cleanup:
            raise RuntimeError("cleanup failed")


class FailingExporter:
    name = "unavailable"

    async def export_trial(
        self, case: EvalCase, record: TrialRecord, *, idempotency_key: str
    ) -> None:
        raise ConnectionError("hosted service unavailable")

    async def export_summary(
        self, summary: object, *, idempotency_key: str
    ) -> None:
        raise ConnectionError("hosted service unavailable")


class BlockingTarget:
    version = "blocking@1"

    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def execute(self, case: EvalCase, context: RunContext) -> object:
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class BlockingCollector:
    name = "blocking"
    version = "1"

    async def collect(self, case: EvalCase, result: object, context: RunContext) -> object:
        await asyncio.Event().wait()
        return {}


class OversizedCollector:
    name = "oversized"
    version = "1"

    async def collect(self, case: EvalCase, result: object, context: RunContext) -> object:
        return {"payload": "x" * 2_000}


@pytest.mark.asyncio
async def test_runner_writes_trials_and_summary(tmp_path: Path) -> None:
    artifact = tmp_path / "results.jsonl"
    cases = [EvalCase(id="one", input={"value": "ok"}, expected={"answer": "OK"})]
    summary = await EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=artifact,
        sandbox_requirements=SandboxRequirements(required=False),
        code_revision="test-revision",
    ).run(cases, run_id="test-run")

    lines = [json.loads(line) for line in artifact.read_text("utf-8").splitlines()]
    trial = TrialRecord.model_validate(lines[0])
    assert summary.pass_rate == 1
    assert trial.status is TrialStatus.PASSED
    assert trial.provenance.code_revision == "test-revision"
    assert trial.result is not None
    assert trial.result.loop is not None
    assert [iteration.node for iteration in trial.result.loop.iterations] == ["answer"]
    assert len(lines) == 2


@pytest.mark.asyncio
async def test_runner_records_failure_without_aborting_suite(tmp_path: Path) -> None:
    cases = [EvalCase(id="wrong", input={"value": "ok"}, expected={"answer": "NO"})]
    summary = await EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=tmp_path / "results.jsonl",
        sandbox_requirements=SandboxRequirements(required=False),
    ).run(cases)
    assert summary.failed == 1
    assert summary.pass_rate == 0


@pytest.mark.asyncio
async def test_runner_always_destroys_provisioned_sandbox(tmp_path: Path) -> None:
    provider = RecordingSandboxProvider()
    artifact = tmp_path / "results.jsonl"
    await EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=artifact,
        sandbox_provider=provider,
    ).run([EvalCase(id="wrong", input={"value": "ok"}, expected={"answer": "NO"})])

    trial = TrialRecord.model_validate_json(artifact.read_text("utf-8").splitlines()[0])
    assert provider.destroyed == provider.provisioned
    assert trial.sandbox is not None
    assert trial.sandbox_cleanup.succeeded


@pytest.mark.asyncio
async def test_cleanup_failure_prevents_false_pass(tmp_path: Path) -> None:
    artifact = tmp_path / "results.jsonl"
    await EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=artifact,
        sandbox_provider=RecordingSandboxProvider(fail_cleanup=True),
    ).run([EvalCase(id="one", input={"value": "ok"}, expected={"answer": "OK"})])

    trial = TrialRecord.model_validate_json(artifact.read_text("utf-8").splitlines()[0])
    assert trial.status is TrialStatus.ERROR
    assert trial.error_type == "SandboxCleanupError"
    assert trial.sandbox_cleanup.attempted
    assert not trial.sandbox_cleanup.succeeded


@pytest.mark.asyncio
async def test_exporter_failure_is_visible_but_does_not_change_pass(tmp_path: Path) -> None:
    summary = await EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=tmp_path / "results.jsonl",
        sandbox_requirements=SandboxRequirements(required=False),
        exporters=[FailingExporter()],
    ).run([EvalCase(id="one", input={"value": "ok"}, expected={"answer": "OK"})])

    assert summary.pass_rate == 1
    assert summary.export_errors
    assert "ConnectionError" in summary.export_errors[0]


@pytest.mark.asyncio
async def test_runner_requires_user_supplied_sandbox_by_default(tmp_path: Path) -> None:
    runner = EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=tmp_path / "results.jsonl",
    )

    with pytest.raises(ValueError, match="user-supplied SandboxProvider"):
        await runner.run([EvalCase(id="one", input={"value": "ok"})])


@pytest.mark.asyncio
async def test_runner_validates_sandbox_capabilities(tmp_path: Path) -> None:
    runner = EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=tmp_path / "results.jsonl",
        sandbox_provider=RecordingSandboxProvider(),
        sandbox_requirements=SandboxRequirements(capabilities=frozenset({"network"})),
    )

    with pytest.raises(ValueError, match="network"):
        await runner.run([EvalCase(id="one", input={"value": "ok"})])


@pytest.mark.asyncio
async def test_absolute_deadline_covers_outcome_collection(tmp_path: Path) -> None:
    summary = await EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        outcome_collectors=[BlockingCollector()],
        budget=Budget(timeout_seconds=0.05),
        artifact_path=tmp_path / "results.jsonl",
        sandbox_requirements=SandboxRequirements(required=False),
    ).run([EvalCase(id="one", input={"value": "ok"}, expected={"answer": "OK"})])

    assert summary.timeouts == 1


@pytest.mark.asyncio
async def test_cancellation_waits_for_shielded_cleanup(tmp_path: Path) -> None:
    target = BlockingTarget()
    provider = RecordingSandboxProvider()
    task = asyncio.create_task(
        EvaluationRunner(
            target=target,  # type: ignore[arg-type]
            graders=[ExactMatchGrader()],
            budget=Budget(),
            artifact_path=tmp_path / "results.jsonl",
            sandbox_provider=provider,
        ).run([EvalCase(id="one", input={})])
    )
    await target.started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.destroyed == provider.provisioned


@pytest.mark.asyncio
async def test_existing_artifact_is_not_truncated(tmp_path: Path) -> None:
    artifact = tmp_path / "results.jsonl"
    artifact.write_text("existing\n", encoding="utf-8")
    runner = EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(),
        artifact_path=artifact,
        sandbox_requirements=SandboxRequirements(required=False),
    )

    with pytest.raises(FileExistsError):
        await runner.run([EvalCase(id="one", input={"value": "ok"})])
    assert artifact.read_text("utf-8") == "existing\n"


@pytest.mark.asyncio
async def test_outcome_evidence_limit_is_enforced(tmp_path: Path) -> None:
    summary = await EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        outcome_collectors=[OversizedCollector()],
        budget=Budget(max_outcome_bytes=1_024),
        artifact_path=tmp_path / "results.jsonl",
        sandbox_requirements=SandboxRequirements(required=False),
    ).run([EvalCase(id="one", input={"value": "ok"}, expected={"answer": "OK"})])

    assert summary.errors == 1


@pytest.mark.asyncio
async def test_complete_trial_artifact_limit_falls_back_to_minimal_record(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "results.jsonl"
    await EvaluationRunner(
        target=graph_target(),
        graders=[ExactMatchGrader()],
        budget=Budget(max_trial_artifact_bytes=10_000),
        artifact_path=artifact,
        sandbox_requirements=SandboxRequirements(required=False),
        prompt_hashes={"oversized": "x" * 20_000},
    ).run([EvalCase(id="one", input={"value": "ok"}, expected={"answer": "OK"})])

    trial = TrialRecord.model_validate_json(artifact.read_text("utf-8").splitlines()[0])
    assert trial.status is TrialStatus.BUDGET_EXCEEDED
    assert trial.error_type == "ArtifactBudgetExceededError"
    assert trial.result is None
