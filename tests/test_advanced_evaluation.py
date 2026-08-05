from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from glyph.security.contracts import RunContext
from glyph.grading.graders import (
    ContextCoverageGrader,
    DuplicateRateGrader,
    LoopEfficiencyGrader,
    OutcomeStateGrader,
    RetrievalMetricsGrader,
    RerankingLatencyGrader,
    TrajectorySubsequenceGrader,
)
from glyph.core.models import (
    Budget,
    EvalCase,
    Grade,
    GraderPolicy,
    LoopIteration,
    LoopObservation,
    RetrievalObservation,
    SandboxRequirements,
    TargetResult,
    TrajectoryEvent,
    TranscriptCapturePolicy,
    TrialStatus,
)
from glyph.grading.judges import CalibratedModelJudge, JudgeDecision
from glyph.security.contracts import RunContext
from glyph.targets.langgraph_target import TrajectoryCallback
from glyph.evaluation.runner import EvaluationRunner


class AlternatingTarget:
    version = "alternating@1"

    async def execute(self, case: EvalCase, context: RunContext) -> TargetResult:
        repetition = int(context.trial_id.split(":")[-2])
        return TargetResult(output={"answer": "ok" if repetition == 0 else "wrong"})


class PartialGrader:
    name = "partial"
    version = "1"

    async def grade(self, case: EvalCase, result: TargetResult) -> Grade:
        passed = result.output == {"answer": "ok"}
        return Grade(
            grader=self.name,
            version=self.version,
            passed=passed,
            score=1.0 if passed else 0.5,
            reason="test",
        )


@pytest.mark.asyncio
async def test_repetitions_and_pass_k_summaries(tmp_path: Path) -> None:
    summary = await EvaluationRunner(
        target=AlternatingTarget(),
        graders=[PartialGrader()],
        grader_policy=GraderPolicy(required=frozenset({"partial"}), pass_threshold=0.5),
        repetitions=2,
        budget=Budget(),
        artifact_path=tmp_path / "results.jsonl",
        sandbox_requirements=SandboxRequirements(required=False),
    ).run([EvalCase(id="case", input={})], run_id="run")

    assert summary.total == 2
    assert summary.average_score == 0.75
    assert summary.pass_at_k == 1.0
    assert summary.pass_power_k == 0.0
    assert summary.suites[case_suite := next(iter(summary.suites))].trials == 2
    assert case_suite.value == "capability"


@pytest.mark.asyncio
async def test_state_trajectory_and_retrieval_graders() -> None:
    case = EvalCase(
        id="rag",
        input={},
        expected={"state": {"saved": True, "count": 2}, "relevant_source_ids": ["b"]},
    )
    result = TargetResult(
        output={"state": {"saved": True, "count": 2}},
        loop=LoopObservation(
            iterations=(LoopIteration(index=0, node="search", outcome="completed"),),
            terminal_reason="completed",
        ),
        retrievals=(
            RetrievalObservation(
                name="search", query_hash="sha256:test", source_ids=("a", "b", "c")
            ),
        ),
        trajectory=(
            TrajectoryEvent(sequence=0, kind="tool_start", name="search"),
            TrajectoryEvent(
                sequence=1,
                kind="retrieval",
                name="search",
                data={"source_ids": ["a", "b", "c"]},
            ),
            TrajectoryEvent(sequence=2, kind="tool_end", name="search"),
        ),
    )

    state = await OutcomeStateGrader().grade(case, result)
    loop = await LoopEfficiencyGrader(max_iterations=3).grade(case, result)
    trajectory = await TrajectorySubsequenceGrader(
        expected=("tool_start:search", "tool_end:search")
    ).grade(case, result)
    retrieval = await RetrievalMetricsGrader(
        k=3, minimum_recall=1.0, minimum_precision=0.3, minimum_mrr=0.5, minimum_ndcg=0.3
    ).grade(case, result)

    assert state.passed
    assert loop.passed
    assert trajectory.passed
    assert retrieval.passed
    assert retrieval.evidence["recall_at_k"] == 1.0
    assert retrieval.evidence["precision_at_k"] == pytest.approx(1 / 3)
    assert retrieval.evidence["mrr"] == 0.5
    assert "ndcg" in retrieval.evidence


@pytest.mark.asyncio
async def test_langgraph_callback_captures_typed_retrieval_contract() -> None:
    class Document:
        def __init__(self) -> None:
            self.metadata = {"id": "document-1"}

    callback = TrajectoryCallback(max_tool_calls=1)
    run_id = uuid4()
    await callback.on_retriever_start(
        {"name": "search"}, "private query", run_id=run_id
    )
    await callback.on_retriever_end([Document()], run_id=run_id, name="search")

    assert len(callback.retrievals) == 1
    assert callback.retrievals[0].source_ids == ("document-1",)
    assert callback.retrievals[0].query_hash.startswith("sha256:")


@pytest.mark.asyncio
async def test_transcript_policy_hashes_tool_payloads_by_default() -> None:
    callback = TrajectoryCallback(max_tool_calls=1)
    run_id = uuid4()
    await callback.on_tool_start(
        {"name": "shell"}, "password=private", run_id=run_id
    )
    await callback.on_tool_end("secret output", run_id=run_id, name="shell")

    assert "input" not in callback.events[0].data
    assert "output" not in callback.events[1].data
    assert callback.events[0].run_id == str(run_id)
    assert callback.events[1].duration_ms is not None


@pytest.mark.asyncio
async def test_transcript_policy_requires_explicit_tool_allowlist() -> None:
    callback = TrajectoryCallback(
        max_tool_calls=1,
        capture_policy=TranscriptCapturePolicy(
            capture_tool_inputs=True,
            capture_tool_outputs=True,
            tool_payload_allowlist=frozenset({"lookup"}),
        ),
    )
    run_id = uuid4()
    await callback.on_tool_start({"name": "lookup"}, "public", run_id=run_id)
    await callback.on_tool_end("result", run_id=run_id, name="lookup")

    assert callback.events[0].data["input"] == "public"
    assert callback.events[1].data["output"] == "result"


@pytest.mark.asyncio
async def test_transcript_policy_records_total_limit_truncation() -> None:
    callback = TrajectoryCallback(
        max_tool_calls=20,
        capture_policy=TranscriptCapturePolicy(max_total_bytes=1_024),
    )
    for _ in range(20):
        await callback.on_tool_start({"name": "tool"}, "input", run_id=uuid4())

    assert callback.transcript_truncated


@pytest.mark.asyncio
async def test_transcript_captures_visible_messages_and_model_errors() -> None:
    callback = TrajectoryCallback(
        max_tool_calls=1,
        capture_policy=TranscriptCapturePolicy(
            capture_messages=True, capture_streaming_chunks=True
        ),
    )
    successful_run = uuid4()
    await callback.on_chat_model_start(
        {"name": "chat"},
        [[HumanMessage(content="hello")]],
        run_id=successful_run,
    )
    await callback.on_llm_new_token("hi", run_id=successful_run, name="chat")
    await callback.on_llm_end(
        LLMResult(
            generations=[[ChatGeneration(message=AIMessage(content="hi"))]]
        ),
        run_id=successful_run,
        name="chat",
    )
    failed_run = uuid4()
    await callback.on_chat_model_start(
        {"name": "chat"}, [[HumanMessage(content="fail")]], run_id=failed_run
    )
    await callback.on_llm_error(RuntimeError("provider failed"), run_id=failed_run)

    kinds = [event.kind for event in callback.events]
    assert kinds == [
        "model_start",
        "model_first_token",
        "model_chunk",
        "model_end",
        "model_start",
        "model_error",
    ]
    assert callback.events[3].data["messages"] == [
        {"role": "ai", "content": "hi"}
    ]


@pytest.mark.asyncio
async def test_model_judge_reserves_run_cost_before_call(tmp_path: Path) -> None:
    calls = 0

    async def judge(case: EvalCase, result: TargetResult) -> JudgeDecision:
        nonlocal calls
        calls += 1
        return JudgeDecision(score=1.0, reason="calibrated", cost_usd=0.04)

    model_judge = CalibratedModelJudge(
        evaluate=judge,
        calibration_id="calibration-2026-07",
        maximum_cost_usd=0.05,
    )
    artifact = tmp_path / "judge.jsonl"
    summary = await EvaluationRunner(
        target=AlternatingTarget(),
        graders=[model_judge],
        budget=Budget(max_concurrency=1, max_judge_cost_usd=0.05),
        artifact_path=artifact,
        sandbox_requirements=SandboxRequirements(required=False),
    ).run([EvalCase(id="one", input={}), EvalCase(id="two", input={})])

    assert calls == 1
    assert summary.errors == 1
    assert summary.judge_cost_usd == 0.04
    records = artifact.read_text("utf-8")
    assert TrialStatus.BUDGET_EXCEEDED.value in records


@pytest.mark.asyncio
async def test_duplicate_rate_grader() -> None:
    """Test duplicate rate grader with and without duplicates."""
    case = EvalCase(id="test-1", input={})
    
    # Test with duplicates
    result_with_duplicates = TargetResult(
        output={
            "retrieved_documents": [
                {"id": "doc1", "content": "content1"},
                {"id": "doc2", "content": "content2"},
                {"id": "doc1", "content": "content1"},  # duplicate
            ]
        },
        trajectory=[],
        outcomes=[],
        retrievals=[],
    )
    
    grader = DuplicateRateGrader(maximum_duplicate_rate=0.1)
    grade = await grader.grade(case, result_with_duplicates)
    
    assert not grade.passed
    assert grade.evidence["duplicate_rate"] == pytest.approx(1/3)
    assert grade.evidence["duplicates"] == 1
    
    # Test without duplicates
    result_no_duplicates = TargetResult(
        output={
            "retrieved_documents": [
                {"id": "doc1", "content": "content1"},
                {"id": "doc2", "content": "content2"},
                {"id": "doc3", "content": "content3"},
            ]
        },
        trajectory=[],
        outcomes=[],
        retrievals=[],
    )
    
    grade = await grader.grade(case, result_no_duplicates)
    assert grade.passed
    assert grade.evidence["duplicate_rate"] == 0.0


@pytest.mark.asyncio
async def test_context_coverage_grader() -> None:
    """Test context coverage grader."""
    case = EvalCase(
        id="test-1",
        input={},
        expected={"required_concepts": ["return policy", "shipping time", "refund process"]}
    )
    
    # Test with good coverage
    result_good = TargetResult(
        output={
            "retrieved_context": "The return policy allows 30 days. Shipping time is 3-5 days. The refund process takes 5-7 business days."
        },
        trajectory=[],
        outcomes=[],
        retrievals=[],
    )
    
    grader = ContextCoverageGrader(minimum_coverage=0.8)
    grade = await grader.grade(case, result_good)
    
    assert grade.passed
    assert grade.evidence["coverage"] == 1.0
    assert len(grade.evidence["covered_concepts"]) == 3
    
    # Test with poor coverage
    result_poor = TargetResult(
        output={
            "retrieved_context": "The return policy allows 30 days."
        },
        trajectory=[],
        outcomes=[],
        retrievals=[],
    )
    
    grade = await grader.grade(case, result_poor)
    assert not grade.passed
    assert grade.evidence["coverage"] == pytest.approx(1/3)


@pytest.mark.asyncio
async def test_reranking_latency_grader() -> None:
    """Test reranking latency grader."""
    case = EvalCase(id="test-1", input={})
    
    # Test with acceptable latency
    result_fast = TargetResult(
        output={"reranking_latency_ms": 500},
        trajectory=[],
        outcomes=[],
        retrievals=[],
    )
    
    grader = RerankingLatencyGrader(maximum_latency_ms=1000.0)
    grade = await grader.grade(case, result_fast)
    
    assert grade.passed
    assert grade.score == 1.0
    
    # Test with high latency
    result_slow = TargetResult(
        output={"reranking_latency_ms": 1500},
        trajectory=[],
        outcomes=[],
        retrievals=[],
    )
    
    grade = await grader.grade(case, result_slow)
    assert not grade.passed
    assert grade.score < 1.0
    assert grade.evidence["latency_ms"] == 1500