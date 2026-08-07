from __future__ import annotations

import asyncio
import json
import os
from collections import Counter
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from pydantic import Field, JsonValue, model_validator

from glyph.core.models import FrozenModel


class HumanReviewDecision(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"


class HumanReviewStatus(StrEnum):
    PENDING = "pending"
    NEEDS_ADJUDICATION = "needs_adjudication"
    COMPLETED = "completed"


class HumanReviewRubric(FrozenModel):
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    version: str = Field(min_length=1)
    dimension: str = Field(min_length=1)
    instructions: str = Field(min_length=1, max_length=20_000)


class HumanReviewPolicy(FrozenModel):
    required_reviews: int = Field(default=2, ge=1, le=20)
    require_adjudication_on_disagreement: bool = True
    minimum_agreement: float = Field(default=1.0, ge=0, le=1)
    max_evidence_bytes: int = Field(default=100_000, ge=1_024, le=10_000_000)


class HumanReviewTask(FrozenModel):
    record_type: Literal["human_review_task"] = "human_review_task"
    task_id: str = Field(default_factory=lambda: f"review-task-{uuid4()}")
    trial_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    trace_id: str | None = None
    rubric: HumanReviewRubric
    policy: HumanReviewPolicy = Field(default_factory=HumanReviewPolicy)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HumanReviewAssignment(FrozenModel):
    task_id: str
    trial_id: str
    case_id: str
    trace_id: str | None = None
    rubric: HumanReviewRubric


class HumanGrade(FrozenModel):
    record_type: Literal["human_grade"] = "human_grade"
    grade_id: str = Field(default_factory=lambda: f"human-grade-{uuid4()}")
    task_id: str = Field(min_length=1)
    reviewer_pseudonym: str = Field(min_length=1, max_length=200)
    decision: HumanReviewDecision
    score: float | None = Field(default=None, ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=20_000)
    evidence: dict[str, JsonValue] = Field(default_factory=dict)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str = Field(default="local", min_length=1)
    source_id: str | None = None
    supersedes_grade_id: str | None = None

    @model_validator(mode="after")
    def validate_score(self) -> HumanGrade:
        if self.decision is HumanReviewDecision.ABSTAIN and self.score is not None:
            raise ValueError("An abstention cannot carry a score")
        if self.decision is not HumanReviewDecision.ABSTAIN and self.score is None:
            raise ValueError("A pass or fail human grade requires a score")
        return self


class HumanAdjudication(FrozenModel):
    record_type: Literal["human_adjudication"] = "human_adjudication"
    adjudication_id: str = Field(default_factory=lambda: f"adjudication-{uuid4()}")
    task_id: str = Field(min_length=1)
    adjudicator_pseudonym: str = Field(min_length=1, max_length=200)
    reviewed_grade_ids: frozenset[str] = Field(min_length=2)
    decision: HumanReviewDecision
    score: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=20_000)
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def reject_abstention(self) -> HumanAdjudication:
        if self.decision is HumanReviewDecision.ABSTAIN:
            raise ValueError("An adjudication must resolve to pass or fail")
        return self


class HumanReviewSummary(FrozenModel):
    task_id: str
    trial_id: str
    rubric_id: str
    rubric_version: str
    status: HumanReviewStatus
    active_reviews: int = Field(ge=0)
    abstentions: int = Field(ge=0)
    agreement: float | None = Field(default=None, ge=0, le=1)
    decision: HumanReviewDecision | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    adjudication_id: str | None = None


class HumanReleasePolicy(FrozenModel):
    required_rubrics: frozenset[str] = Field(min_length=1)
    require_passing_decision: bool = True
    minimum_cohen_kappa: float | None = Field(default=None, ge=-1, le=1)
    reviewer_pair: tuple[str, str] | None = None

    @model_validator(mode="after")
    def require_reviewer_pair_for_kappa(self) -> HumanReleasePolicy:
        if self.minimum_cohen_kappa is not None and self.reviewer_pair is None:
            raise ValueError("A reviewer pair is required for a kappa release threshold")
        if self.reviewer_pair is not None and self.reviewer_pair[0] == self.reviewer_pair[1]:
            raise ValueError("Kappa requires two distinct reviewers")
        return self


class HumanReleaseDecision(FrozenModel):
    allowed: bool
    reasons: tuple[str, ...]
    summaries: tuple[HumanReviewSummary, ...]
    cohen_kappa: float | None = Field(default=None, ge=-1, le=1)


class HumanGrader(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    async def grade(self, assignment: HumanReviewAssignment) -> HumanGrade: ...


class HumanEvaluationLedger:
    """Append-only canonical evidence for asynchronous human evaluation."""

    def __init__(
        self, path: Path, *, resume: bool = False, overwrite: bool = False
    ) -> None:
        if resume and overwrite:
            raise ValueError("resume and overwrite are mutually exclusive")
        self.path = path
        self.resume = resume
        self.overwrite = overwrite
        self._lock = asyncio.Lock()
        self._tasks: dict[str, HumanReviewTask] = {}
        self._grades: list[HumanGrade] = []
        self._adjudications: list[HumanAdjudication] = []

    async def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._initialize_sync)

    async def create_task(self, task: HumanReviewTask) -> None:
        if task.task_id in self._tasks:
            raise ValueError(f"Duplicate human review task {task.task_id!r}")
        await self._append(task)
        self._tasks[task.task_id] = task

    def assignment(self, task_id: str) -> HumanReviewAssignment:
        task = self._task(task_id)
        return HumanReviewAssignment(
            task_id=task.task_id,
            trial_id=task.trial_id,
            case_id=task.case_id,
            trace_id=task.trace_id,
            rubric=task.rubric,
        )

    async def submit_grade(self, grade: HumanGrade) -> None:
        task = self._task(grade.task_id)
        evidence_bytes = len(
            json.dumps(grade.evidence, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        if evidence_bytes > task.policy.max_evidence_bytes:
            raise ValueError(
                f"Human grade evidence exceeds {task.policy.max_evidence_bytes} bytes"
            )
        if any(existing.grade_id == grade.grade_id for existing in self._grades):
            raise ValueError(f"Duplicate human grade {grade.grade_id!r}")
        if grade.source_id is not None and any(
            existing.source == grade.source and existing.source_id == grade.source_id
            for existing in self._grades
        ):
            raise ValueError(f"Duplicate source grade {grade.source!r}/{grade.source_id!r}")
        active = {
            item.reviewer_pseudonym: item for item in self.active_grades(grade.task_id)
        }
        previous = active.get(grade.reviewer_pseudonym)
        if previous is not None and grade.supersedes_grade_id != previous.grade_id:
            raise ValueError("A revised human grade must explicitly supersede the active grade")
        if previous is None and grade.supersedes_grade_id is not None:
            raise ValueError("No active human grade exists to supersede")
        await self._append(grade)
        self._grades.append(grade)

    async def adjudicate(self, adjudication: HumanAdjudication) -> None:
        self._task(adjudication.task_id)
        active_ids = {grade.grade_id for grade in self.active_grades(adjudication.task_id)}
        if not adjudication.reviewed_grade_ids.issubset(active_ids):
            raise ValueError("Adjudication must reference active grades for the same task")
        if any(
            existing.adjudication_id == adjudication.adjudication_id
            for existing in self._adjudications
        ):
            raise ValueError(f"Duplicate adjudication {adjudication.adjudication_id!r}")
        await self._append(adjudication)
        self._adjudications.append(adjudication)

    def active_grades(self, task_id: str) -> tuple[HumanGrade, ...]:
        active: dict[str, HumanGrade] = {}
        for grade in self._grades:
            if grade.task_id == task_id:
                active[grade.reviewer_pseudonym] = grade
        return tuple(active.values())

    def has_source_grade(self, source: str, source_id: str) -> bool:
        return any(
            grade.source == source and grade.source_id == source_id
            for grade in self._grades
        )

    def summary(self, task_id: str) -> HumanReviewSummary:
        task = self._task(task_id)
        grades = self.active_grades(task_id)
        substantive = tuple(
            grade for grade in grades if grade.decision is not HumanReviewDecision.ABSTAIN
        )
        abstentions = len(grades) - len(substantive)
        if len(substantive) < task.policy.required_reviews:
            return self._summary(task, HumanReviewStatus.PENDING, grades, abstentions)

        counts = Counter(grade.decision for grade in substantive)
        agreement = max(counts.values()) / len(substantive)
        adjudication = next(
            (
                item
                for item in reversed(self._adjudications)
                if item.task_id == task_id
                and item.reviewed_grade_ids.issubset({grade.grade_id for grade in grades})
            ),
            None,
        )
        disagreed = len(counts) > 1 or agreement < task.policy.minimum_agreement
        if disagreed and task.policy.require_adjudication_on_disagreement:
            if adjudication is None:
                return self._summary(
                    task,
                    HumanReviewStatus.NEEDS_ADJUDICATION,
                    grades,
                    abstentions,
                    agreement=agreement,
                )
            return self._summary(
                task,
                HumanReviewStatus.COMPLETED,
                grades,
                abstentions,
                agreement=agreement,
                decision=adjudication.decision,
                score=adjudication.score,
                adjudication_id=adjudication.adjudication_id,
            )
        if len(counts) > 1:
            return self._summary(
                task,
                HumanReviewStatus.NEEDS_ADJUDICATION,
                grades,
                abstentions,
                agreement=agreement,
            )
        return self._summary(
            task,
            HumanReviewStatus.COMPLETED,
            grades,
            abstentions,
            agreement=agreement,
            decision=substantive[0].decision,
            score=sum(grade.score or 0 for grade in substantive) / len(substantive),
        )

    def evaluate_release(
        self, task_ids: tuple[str, ...], policy: HumanReleasePolicy
    ) -> HumanReleaseDecision:
        summaries = tuple(self.summary(task_id) for task_id in task_ids)
        reasons: list[str] = []
        present_rubrics = {summary.rubric_id for summary in summaries}
        for rubric in sorted(policy.required_rubrics - present_rubrics):
            reasons.append(f"Required human rubric {rubric!r} is missing")
        for summary in summaries:
            if summary.rubric_id not in policy.required_rubrics:
                continue
            if summary.status is not HumanReviewStatus.COMPLETED:
                reasons.append(
                    f"Human review {summary.task_id!r} is {summary.status.value}"
                )
            elif (
                policy.require_passing_decision
                and summary.decision is not HumanReviewDecision.PASS
            ):
                reasons.append(f"Human review {summary.task_id!r} did not pass")
        kappa = None
        if policy.reviewer_pair is not None:
            kappa = self.cohen_kappa(*policy.reviewer_pair, task_ids=task_ids)
            if kappa is None:
                reasons.append("Cohen's kappa is unavailable for the required reviewer pair")
            elif policy.minimum_cohen_kappa is not None and kappa < policy.minimum_cohen_kappa:
                reasons.append(
                    f"Cohen's kappa {kappa:.3f} is below {policy.minimum_cohen_kappa:.3f}"
                )
        return HumanReleaseDecision(
            allowed=not reasons,
            reasons=tuple(reasons),
            summaries=summaries,
            cohen_kappa=kappa,
        )

    def cohen_kappa(
        self, reviewer_a: str, reviewer_b: str, *, task_ids: tuple[str, ...]
    ) -> float | None:
        pairs: list[tuple[HumanReviewDecision, HumanReviewDecision]] = []
        for task_id in task_ids:
            by_reviewer = {
                grade.reviewer_pseudonym: grade for grade in self.active_grades(task_id)
            }
            left = by_reviewer.get(reviewer_a)
            right = by_reviewer.get(reviewer_b)
            if (
                left is not None
                and right is not None
                and left.decision is not HumanReviewDecision.ABSTAIN
                and right.decision is not HumanReviewDecision.ABSTAIN
            ):
                pairs.append((left.decision, right.decision))
        if not pairs:
            return None
        observed = sum(left is right for left, right in pairs) / len(pairs)
        left_counts = Counter(left for left, _ in pairs)
        right_counts = Counter(right for _, right in pairs)
        expected = sum(
            left_counts[decision] / len(pairs) * right_counts[decision] / len(pairs)
            for decision in (HumanReviewDecision.PASS, HumanReviewDecision.FAIL)
        )
        if expected == 1:
            return 1.0 if observed == 1 else None
        return (observed - expected) / (1 - expected)

    def _initialize_sync(self) -> None:
        if self.resume:
            if self.path.exists():
                self._load_sync()
            else:
                self.path.touch(exist_ok=False)
            return
        mode = "w" if self.overwrite else "x"
        with self.path.open(mode, encoding="utf-8", newline="\n"):
            pass

    def _load_sync(self) -> None:
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            try:
                payload = json.loads(line)
                record_type = payload.get("record_type")
                if record_type == "human_review_task":
                    task = HumanReviewTask.model_validate(payload)
                    self._tasks[task.task_id] = task
                elif record_type == "human_grade":
                    self._grades.append(HumanGrade.model_validate(payload))
                elif record_type == "human_adjudication":
                    self._adjudications.append(HumanAdjudication.model_validate(payload))
                else:
                    raise ValueError(f"unknown record_type {record_type!r}")
            except (ValueError, TypeError) as error:
                raise ValueError(
                    f"Invalid human evaluation artifact at line {line_number}"
                ) from error

    async def _append(
        self, record: HumanReviewTask | HumanGrade | HumanAdjudication
    ) -> None:
        payload = record.model_dump_json(exclude_none=True) + "\n"
        async with self._lock:
            await asyncio.to_thread(self._append_sync, payload)

    def _append_sync(self, payload: str) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    def _task(self, task_id: str) -> HumanReviewTask:
        try:
            return self._tasks[task_id]
        except KeyError as error:
            raise ValueError(f"Unknown human review task {task_id!r}") from error

    @staticmethod
    def _summary(
        task: HumanReviewTask,
        status: HumanReviewStatus,
        grades: tuple[HumanGrade, ...],
        abstentions: int,
        *,
        agreement: float | None = None,
        decision: HumanReviewDecision | None = None,
        score: float | None = None,
        adjudication_id: str | None = None,
    ) -> HumanReviewSummary:
        return HumanReviewSummary(
            task_id=task.task_id,
            trial_id=task.trial_id,
            rubric_id=task.rubric.id,
            rubric_version=task.rubric.version,
            status=status,
            active_reviews=len(grades),
            abstentions=abstentions,
            agreement=agreement,
            decision=decision,
            score=score,
            adjudication_id=adjudication_id,
        )