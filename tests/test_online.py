from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from glyph.grading.graders import ExactMatchGrader
from glyph.core.domain_models import (
    EvalCase,
    OnlineEvaluationPolicy,
    OnlineEvaluationStatus,
    TargetResult,
)
from glyph.evaluation.online import InMemoryOnlineCostLedger, OnlineEvaluator


def policy(**updates: object) -> OnlineEvaluationPolicy:
    values: dict[str, object] = {
        "enabled": True,
        "privacy_review_id": "privacy-1",
        "sampling_rate": 1.0,
        "retention_days": 30,
        "maximum_monthly_cost_usd": 1.0,
        "allowed_project": "production-evals",
    }
    values.update(updates)
    return OnlineEvaluationPolicy.model_validate(values)


@pytest.mark.asyncio
async def test_online_evaluator_enforces_project_and_retention() -> None:
    evaluator = OnlineEvaluator(policy=policy(), graders=(ExactMatchGrader(),))
    case = EvalCase(id="one", input={}, expected={"answer": "ok"})
    result = TargetResult(output={"answer": "ok"})

    wrong_project = await evaluator.evaluate(
        trace_id="trace-1",
        project="other",
        observed_at=datetime.now(UTC),
        case=case,
        result=result,
    )
    expired = await evaluator.evaluate(
        trace_id="trace-2",
        project="production-evals",
        observed_at=datetime.now(UTC) - timedelta(days=31),
        case=case,
        result=result,
    )

    assert wrong_project.status is OnlineEvaluationStatus.REJECTED
    assert expired.status is OnlineEvaluationStatus.REJECTED


@pytest.mark.asyncio
async def test_online_evaluator_runs_sampled_trace() -> None:
    evaluator = OnlineEvaluator(
        policy=policy(),
        graders=(ExactMatchGrader(),),
        cost_ledger=InMemoryOnlineCostLedger(),
    )
    decision = await evaluator.evaluate(
        trace_id="trace-1",
        project="production-evals",
        observed_at=datetime.now(UTC),
        case=EvalCase(id="one", input={}, expected={"answer": "ok"}),
        result=TargetResult(output={"answer": "ok"}),
    )

    assert decision.status is OnlineEvaluationStatus.EVALUATED
    assert decision.sampled
    assert decision.grades[0].passed


@pytest.mark.asyncio
async def test_online_evaluator_deterministically_skips_unsampled_trace() -> None:
    evaluator = OnlineEvaluator(
        policy=policy(sampling_rate=0.000000001), graders=(ExactMatchGrader(),)
    )
    decision = await evaluator.evaluate(
        trace_id="trace-not-sampled",
        project="production-evals",
        observed_at=datetime.now(UTC),
        case=EvalCase(id="one", input={}),
        result=TargetResult(output={}),
    )

    assert decision.status is OnlineEvaluationStatus.NOT_SAMPLED