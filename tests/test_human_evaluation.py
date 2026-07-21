from __future__ import annotations

from pathlib import Path

import pytest

from langgraph_eval.human import (
    HumanAdjudication,
    HumanEvaluationLedger,
    HumanGrade,
    HumanReleasePolicy,
    HumanReviewDecision,
    HumanReviewRubric,
    HumanReviewStatus,
    HumanReviewTask,
)


def task(task_id: str = "task-1", trial_id: str = "trial-immutable") -> HumanReviewTask:
    return HumanReviewTask(
        task_id=task_id,
        trial_id=trial_id,
        case_id="case-1",
        rubric=HumanReviewRubric(
            id="correctness",
            version="1.0",
            dimension="Task correctness",
            instructions="Pass only when the observable outcome is correct.",
        ),
    )


def grade(
    task_id: str, reviewer: str, decision: HumanReviewDecision, score: float
) -> HumanGrade:
    return HumanGrade(
        task_id=task_id,
        reviewer_pseudonym=reviewer,
        decision=decision,
        score=score,
        confidence=0.9,
        reason=f"{reviewer} decision",
    )


@pytest.mark.asyncio
async def test_blind_reviews_require_adjudication_and_gate_release(tmp_path: Path) -> None:
    artifact = tmp_path / "human-reviews.jsonl"
    ledger = HumanEvaluationLedger(artifact)
    await ledger.initialize()
    review_task = task()
    await ledger.create_task(review_task)

    assignment = ledger.assignment(review_task.task_id)
    assert assignment.trial_id == "trial-immutable"
    assert not hasattr(assignment, "grades")

    left = grade(review_task.task_id, "reviewer-a", HumanReviewDecision.PASS, 1.0)
    right = grade(review_task.task_id, "reviewer-b", HumanReviewDecision.FAIL, 0.0)
    await ledger.submit_grade(left)
    await ledger.submit_grade(right)

    unresolved = ledger.summary(review_task.task_id)
    assert unresolved.status is HumanReviewStatus.NEEDS_ADJUDICATION
    blocked = ledger.evaluate_release(
        (review_task.task_id,), HumanReleasePolicy(required_rubrics={"correctness"})
    )
    assert not blocked.allowed

    await ledger.adjudicate(
        HumanAdjudication(
            task_id=review_task.task_id,
            adjudicator_pseudonym="lead-reviewer",
            reviewed_grade_ids={left.grade_id, right.grade_id},
            decision=HumanReviewDecision.PASS,
            score=1.0,
            reason="The reference outcome confirms the result.",
        )
    )

    completed = ledger.summary(review_task.task_id)
    assert completed.status is HumanReviewStatus.COMPLETED
    assert completed.decision is HumanReviewDecision.PASS
    assert ledger.evaluate_release(
        (review_task.task_id,), HumanReleasePolicy(required_rubrics={"correctness"})
    ).allowed
    assert "trial-immutable" in artifact.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_revisions_are_explicit_and_ledger_resumes(tmp_path: Path) -> None:
    artifact = tmp_path / "human-reviews.jsonl"
    ledger = HumanEvaluationLedger(artifact)
    await ledger.initialize()
    await ledger.create_task(task())
    original = grade("task-1", "reviewer-a", HumanReviewDecision.FAIL, 0.0)
    await ledger.submit_grade(original)

    with pytest.raises(ValueError, match="explicitly supersede"):
        await ledger.submit_grade(
            grade("task-1", "reviewer-a", HumanReviewDecision.PASS, 1.0)
        )
    await ledger.submit_grade(
        grade("task-1", "reviewer-a", HumanReviewDecision.PASS, 1.0).model_copy(
            update={"supersedes_grade_id": original.grade_id}
        )
    )

    resumed = HumanEvaluationLedger(artifact, resume=True)
    await resumed.initialize()
    active = resumed.active_grades("task-1")
    assert len(active) == 1
    assert active[0].decision is HumanReviewDecision.PASS


@pytest.mark.asyncio
async def test_cohen_kappa_uses_paired_active_reviews(tmp_path: Path) -> None:
    ledger = HumanEvaluationLedger(tmp_path / "human-reviews.jsonl")
    await ledger.initialize()
    decisions = (
        (HumanReviewDecision.PASS, HumanReviewDecision.PASS),
        (HumanReviewDecision.PASS, HumanReviewDecision.FAIL),
        (HumanReviewDecision.FAIL, HumanReviewDecision.FAIL),
        (HumanReviewDecision.FAIL, HumanReviewDecision.FAIL),
    )
    task_ids = tuple(f"task-{index}" for index in range(len(decisions)))
    for task_id, (left, right) in zip(task_ids, decisions, strict=True):
        await ledger.create_task(task(task_id, f"trial-{task_id}"))
        await ledger.submit_grade(grade(task_id, "reviewer-a", left, float(left == "pass")))
        await ledger.submit_grade(grade(task_id, "reviewer-b", right, float(right == "pass")))

    assert ledger.cohen_kappa("reviewer-a", "reviewer-b", task_ids=task_ids) == pytest.approx(
        0.5
    )