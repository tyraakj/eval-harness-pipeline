from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import partial
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from langgraph_eval.human import (
    HumanEvaluationLedger,
    HumanGrade,
    HumanReviewDecision,
)
from langgraph_eval.models import EvalCase, RunSummary, TrialRecord, TrialStatus
from langgraph_eval.utils import sanitize


class LangSmithExporter:
    """Optional hosted projection of canonical local evaluation evidence."""

    name = "langsmith"

    def __init__(
        self,
        *,
        dataset_name: str,
        experiment_prefix: str = "local-evaluation",
        client: Any | None = None,
        annotation_queue_id: str | None = None,
        annotate_statuses: frozenset[TrialStatus] = frozenset(
            {TrialStatus.FAILED, TrialStatus.ERROR, TrialStatus.BUDGET_EXCEEDED}
        ),
    ) -> None:
        if not dataset_name:
            raise ValueError("LangSmith dataset name is required")
        if client is None:
            try:
                from langsmith import Client
            except ImportError as error:
                raise RuntimeError(
                    "Install the LangSmith integration with 'uv sync --extra langsmith'"
                ) from error
            client = Client()
        self.client = client
        self.dataset_name = dataset_name
        self.experiment_prefix = experiment_prefix
        self.annotation_queue_id = annotation_queue_id
        self.annotate_statuses = annotate_statuses
        self._mirrored_cases: dict[str, str] = {}
        self._experiment_projects: set[str] = set()
        self._dataset_lock = asyncio.Lock()

    async def export_trial(
        self, case: EvalCase, record: TrialRecord, *, idempotency_key: str
    ) -> None:
        example_id = await self._mirror_case(case)
        if record.result is None or record.result.trace_id is None:
            return
        trace_id = record.result.trace_id
        experiment_run_id = uuid5(NAMESPACE_URL, f"langgraph-eval:{record.trial_id}")
        project_name = await self._ensure_experiment(record.run_id)
        await asyncio.to_thread(
            self.client.create_run,
            name=record.case_id,
            inputs={"input_hash": record.input_hash},
            outputs=sanitize(
                {
                    "output": record.result.output,
                    "status": record.status.value,
                    "score": record.score,
                }
            ),
            run_type="chain",
            project_name=project_name,
            id=experiment_run_id,
            start_time=record.started_at,
            end_time=record.started_at,
            reference_example_id=example_id,
            extra={
                "metadata": {
                    "local_run_id": record.run_id,
                    "local_trial_id": record.trial_id,
                    "source_trace_id": trace_id,
                }
            },
        )
        for grade in record.grades:
            await asyncio.to_thread(
                self.client.create_feedback,
                run_id=experiment_run_id,
                key=f"eval.{grade.grader}",
                score=grade.score,
                value=grade.passed,
                comment=grade.reason,
                source_info={
                    "grader_version": grade.version,
                    "local_run_id": record.run_id,
                    "local_trial_id": record.trial_id,
                },
                feedback_id=uuid5(
                    NAMESPACE_URL, f"{idempotency_key}:{grade.grader}"
                ),
            )
        if self.annotation_queue_id and record.status in self.annotate_statuses:
            await asyncio.to_thread(
                partial(
                    self.client.add_runs_to_annotation_queue,
                    self.annotation_queue_id,
                    run_ids=[trace_id],
                )
            )

    async def export_summary(
        self, summary: RunSummary, *, idempotency_key: str
    ) -> None:
        return None

    async def create_annotation_queue(
        self, *, name: str, rubric_instructions: str, description: str | None = None
    ) -> str:
        queue = await asyncio.to_thread(
            self.client.create_annotation_queue,
            name=name,
            description=description,
            rubric_instructions=rubric_instructions,
        )
        return str(queue.id)

    async def promote_trace_to_dataset(
        self,
        trace_id: str,
        *,
        metadata: Mapping[str, Any] | None = None,
        split: str = "regression",
    ) -> str:
        dataset = await self._ensure_dataset()
        example = await asyncio.to_thread(
            self.client.create_example,
            dataset_id=dataset.id,
            source_run_id=trace_id,
            use_source_run_io=True,
            metadata=sanitize(metadata or {}),
            split=split,
        )
        return str(example.id)

    async def import_human_reviews(
        self,
        *,
        trace_id: str,
        task_id: str,
        ledger: HumanEvaluationLedger,
    ) -> int:
        """Import completed, structured annotation feedback into the local ledger."""
        assignment = ledger.assignment(task_id)
        feedback_key = f"human.{assignment.rubric.id}"
        feedback_items = await asyncio.to_thread(
            lambda: list(
                self.client.list_feedback(
                    run_ids=[trace_id], feedback_key=[feedback_key]
                )
            )
        )
        imported = 0
        for feedback in feedback_items:
            source_id = str(self._required_feedback_field(feedback, "id"))
            if ledger.has_source_grade("langsmith", source_id):
                continue
            source_info = self._required_feedback_mapping(feedback, "source_info")
            rubric_version = source_info.get("rubric_version")
            if rubric_version != assignment.rubric.version:
                raise ValueError(
                    f"LangSmith feedback {source_id!r} has a mismatched rubric version"
                )
            reviewer = source_info.get("reviewer_pseudonym")
            confidence = source_info.get("confidence")
            if not isinstance(reviewer, str) or not reviewer:
                raise ValueError(
                    f"LangSmith feedback {source_id!r} lacks a reviewer pseudonym"
                )
            if not isinstance(confidence, int | float) or isinstance(confidence, bool):
                raise ValueError(f"LangSmith feedback {source_id!r} lacks confidence")
            comment = self._required_feedback_field(feedback, "comment")
            if not isinstance(comment, str) or not comment:
                raise ValueError(f"LangSmith feedback {source_id!r} lacks a rationale")
            decision = self._human_decision(
                self._required_feedback_field(feedback, "value"), source_id
            )
            raw_score = getattr(feedback, "score", None)
            score = None if decision is HumanReviewDecision.ABSTAIN else raw_score
            if score is None and decision is not HumanReviewDecision.ABSTAIN:
                score = 1.0 if decision is HumanReviewDecision.PASS else 0.0
            raw_evidence = source_info.get("evidence", {})
            evidence = sanitize(raw_evidence)
            if not isinstance(evidence, dict):
                raise ValueError(
                    f"LangSmith feedback {source_id!r} evidence must be an object"
                )
            submitted_at = getattr(feedback, "created_at", datetime.now(UTC))
            previous = next(
                (
                    grade
                    for grade in ledger.active_grades(task_id)
                    if grade.reviewer_pseudonym == reviewer
                ),
                None,
            )
            await ledger.submit_grade(
                HumanGrade(
                    task_id=task_id,
                    reviewer_pseudonym=reviewer,
                    decision=decision,
                    score=score,
                    confidence=float(confidence),
                    reason=comment,
                    evidence=evidence,
                    submitted_at=submitted_at,
                    source="langsmith",
                    source_id=source_id,
                    supersedes_grade_id=(previous.grade_id if previous is not None else None),
                )
            )
            imported += 1
        return imported

    @staticmethod
    def _required_feedback_field(feedback: Any, name: str) -> Any:
        value = getattr(feedback, name, None)
        if value is None:
            raise ValueError(f"LangSmith feedback lacks required field {name!r}")
        return value

    @classmethod
    def _required_feedback_mapping(cls, feedback: Any, name: str) -> Mapping[str, Any]:
        value = cls._required_feedback_field(feedback, name)
        if not isinstance(value, Mapping):
            raise ValueError(f"LangSmith feedback field {name!r} must be an object")
        return value

    @staticmethod
    def _human_decision(value: Any, source_id: str) -> HumanReviewDecision:
        if isinstance(value, bool):
            return HumanReviewDecision.PASS if value else HumanReviewDecision.FAIL
        if isinstance(value, str):
            try:
                return HumanReviewDecision(value.lower())
            except ValueError as error:
                raise ValueError(
                    f"LangSmith feedback {source_id!r} has an invalid decision"
                ) from error
        raise ValueError(f"LangSmith feedback {source_id!r} lacks an explicit decision")

    async def _mirror_case(self, case: EvalCase) -> str:
        async with self._dataset_lock:
            if case.id in self._mirrored_cases:
                return self._mirrored_cases[case.id]
            dataset = await self._ensure_dataset()
            example_uuid = uuid5(NAMESPACE_URL, f"{self.dataset_name}:{case.id}")
            payload = {
                "inputs": sanitize(case.input),
                "outputs": sanitize(case.expected),
                "metadata": sanitize(
                    {
                        "local_case_id": case.id,
                        "suite": case.suite.value,
                        "tags": sorted(case.tags),
                        **case.metadata,
                    }
                ),
            }
            try:
                await asyncio.to_thread(self.client.read_example, example_uuid)
                await asyncio.to_thread(
                    partial(
                        self.client.update_example,
                        example_uuid,
                        dataset_id=dataset.id,
                        **payload,
                    )
                )
            except Exception as error:
                if type(error).__name__ not in {"LangSmithNotFoundError", "NotFoundError"}:
                    raise
                await asyncio.to_thread(
                    self.client.create_example,
                    dataset_id=dataset.id,
                    example_id=example_uuid,
                    **payload,
                )
            example_id = str(example_uuid)
            self._mirrored_cases[case.id] = example_id
            return example_id

    async def _ensure_experiment(self, run_id: str) -> str:
        project_name = f"{self.experiment_prefix}-{run_id}"
        async with self._dataset_lock:
            if project_name in self._experiment_projects:
                return project_name
            dataset = await self._ensure_dataset()
            await asyncio.to_thread(
                self.client.create_project,
                project_name,
                description="Projection of canonical local evaluation results",
                metadata={"local_run_id": run_id, "canonical_source": "local-jsonl"},
                upsert=True,
                reference_dataset_id=dataset.id,
            )
            self._experiment_projects.add(project_name)
            return project_name

    async def _ensure_dataset(self) -> Any:
        try:
            return await asyncio.to_thread(
                self.client.read_dataset, dataset_name=self.dataset_name
            )
        except Exception as error:
            if type(error).__name__ not in {"LangSmithNotFoundError", "NotFoundError"}:
                raise
            return await asyncio.to_thread(
                self.client.create_dataset,
                self.dataset_name,
                description="Sanitized mirror of local evaluation cases",
                metadata={"canonical_source": "local-jsonl"},
            )