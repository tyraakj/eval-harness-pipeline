from __future__ import annotations

import asyncio
import importlib.metadata
import os
import time
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from langgraph_eval.artifacts import JsonlArtifactWriter
from langgraph_eval.contracts import (
    EvaluationExporter,
    Grader,
    OutcomeCollector,
    RunContext,
    SandboxProvider,
    Target,
)
from langgraph_eval.exporting import ExportDispatcher
from langgraph_eval.langgraph_target import BudgetExceededError
from langgraph_eval.models import (
    Budget,
    EvalCase,
    EvaluationSuite,
    ExportPolicy,
    Grade,
    GraderPolicy,
    OutcomeObservation,
    Provenance,
    RunSummary,
    SandboxCleanup,
    SandboxRequirements,
    SandboxSession,
    SuiteSummary,
    SuiteType,
    TargetResult,
    TrialRecord,
    TrialStatus,
)
from langgraph_eval.sandbox import NoopSandboxProvider
from langgraph_eval.telemetry import EvaluationTelemetry
from langgraph_eval.utils import canonical_json, content_hash, sanitize, sanitize_text

DEFAULT_TRACKED_METRICS = frozenset(
    {"turns", "tool_calls", "tokens", "latency", "cost", "loop_iterations", "retrievals"}
)


class EvaluationRunner:
    def __init__(
        self,
        *,
        target: Target,
        graders: Sequence[Grader],
        budget: Budget,
        artifact_path: Path,
        suite: EvaluationSuite | None = None,
        outcome_collectors: Sequence[OutcomeCollector] = (),
        grader_policy: GraderPolicy | None = None,
        repetitions: int = 1,
        telemetry: EvaluationTelemetry | None = None,
        sandbox_provider: SandboxProvider | None = None,
        sandbox_requirements: SandboxRequirements | None = None,
        sandbox_cleanup_timeout_seconds: float = 30.0,
        exporters: Sequence[EvaluationExporter] = (),
        export_policy: ExportPolicy | None = None,
        prompt_hashes: dict[str, str] | None = None,
        code_revision: str | None = None,
        overwrite_artifact: bool = False,
    ) -> None:
        if not graders:
            raise ValueError("At least one grader is required")
        if repetitions < 1:
            raise ValueError("Repetitions must be at least one")
        if sandbox_cleanup_timeout_seconds <= 0:
            raise ValueError("Sandbox cleanup timeout must be positive")
        self.target = target
        self.graders = tuple(graders)
        self._graders_by_name = {grader.name: grader for grader in graders}
        if len(self._graders_by_name) != len(self.graders):
            raise ValueError("Grader names must be unique")
        self.suite = suite or EvaluationSuite(id="default", version="1.0.0")
        self.outcome_collectors = tuple(outcome_collectors)
        collector_names = [collector.name for collector in self.outcome_collectors]
        if len(collector_names) != len(set(collector_names)):
            raise ValueError("Outcome collector names must be unique")
        self.budget = budget
        self.writer = JsonlArtifactWriter(
            artifact_path,
            overwrite=overwrite_artifact,
        )
        self.grader_policy = grader_policy or GraderPolicy(
            required=frozenset(grader.name for grader in graders)
        )
        grader_names = set(self._graders_by_name)
        unknown_policy_names = (
            set(self.grader_policy.required) | set(self.grader_policy.weights)
        ) - grader_names
        if unknown_policy_names:
            raise ValueError(f"Grader policy references unknown graders: {unknown_policy_names}")
        unknown_suite_graders = set(self.suite.default_graders) - grader_names
        if unknown_suite_graders:
            raise ValueError(f"Suite references unknown graders: {unknown_suite_graders}")
        unknown_suite_metrics = set(self.suite.tracked_metrics) - DEFAULT_TRACKED_METRICS
        if unknown_suite_metrics:
            raise ValueError(f"Suite references unknown metrics: {unknown_suite_metrics}")
        self.repetitions = repetitions
        self.telemetry = telemetry or EvaluationTelemetry()
        self.sandbox_provider = sandbox_provider or NoopSandboxProvider()
        self.sandbox_requirements = sandbox_requirements or SandboxRequirements()
        self.sandbox_cleanup_timeout_seconds = sandbox_cleanup_timeout_seconds
        self.exporters = tuple(exporters)
        self.export_policy = export_policy or ExportPolicy()
        exporter_names = [exporter.name for exporter in self.exporters]
        if len(exporter_names) != len(set(exporter_names)):
            raise ValueError("Exporter names must be unique")
        self.prompt_hashes = prompt_hashes or {}
        environment_revision = os.getenv("GIT_COMMIT")
        self.code_revision = code_revision or environment_revision or "unknown"

    async def run(self, cases: Sequence[EvalCase], *, run_id: str | None = None) -> RunSummary:
        if not cases:
            raise ValueError("At least one evaluation case is required")
        case_ids = [case.id for case in cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("Evaluation case IDs must be unique")
        for case in cases:
            unknown_case_graders = set(case.graders) - set(self._graders_by_name)
            if unknown_case_graders:
                raise ValueError(
                    f"Case {case.id!r} references unknown graders: {unknown_case_graders}"
                )
            unknown_case_metrics = set(case.tracked_metrics) - DEFAULT_TRACKED_METRICS
            if unknown_case_metrics:
                raise ValueError(
                    f"Case {case.id!r} references unknown metrics: {unknown_case_metrics}"
                )
        self._validate_sandbox(cases)

        active_run_id = run_id or f"run-{uuid4()}"
        started_at = datetime.now(UTC)
        await self.writer.initialize()
        semaphore = asyncio.Semaphore(self.budget.max_concurrency)
        self._judge_cost_usd = 0.0
        self._judge_cost_lock = asyncio.Lock()
        dispatcher = ExportDispatcher(
            self.exporters, self.export_policy, telemetry=self.telemetry
        )
        await dispatcher.start()
        dataset_hash = content_hash([case.model_dump(mode="json") for case in cases])

        async def bounded(case: EvalCase, repetition_index: int) -> TrialRecord:
            async with semaphore:
                with self.telemetry.span(
                    "evaluation.trial",
                    {
                        "evaluation.run.id": active_run_id,
                        "evaluation.case.id": case.id,
                        "evaluation.trial.repetition": repetition_index,
                        "evaluation.suite": case.suite.value,
                    },
                ):
                    record = await self._run_trial(
                        active_run_id, case, dataset_hash, repetition_index
                    )
                    self.telemetry.record_trial(record, target_version=self.target.version)
                await self.writer.append(
                    record, max_record_bytes=self.budget.max_trial_artifact_bytes
                )
                await dispatcher.submit_trial(case, record)
                return record

        try:
            with self.telemetry.span(
                "evaluation.run",
                {
                    "evaluation.run.id": active_run_id,
                    "evaluation.case.count": len(cases),
                    "evaluation.repetitions": self.repetitions,
                },
            ):
                records = await asyncio.gather(
                    *(
                        bounded(case, repetition_index)
                        for case in cases
                        for repetition_index in range(self.repetitions)
                    )
                )
        except BaseException:
            await self._close_dispatcher(dispatcher)
            raise
        passed = sum(record.status == TrialStatus.PASSED for record in records)
        failed = sum(record.status == TrialStatus.FAILED for record in records)
        errors = sum(
            record.status in {TrialStatus.ERROR, TrialStatus.BUDGET_EXCEEDED}
            for record in records
        )
        timeouts = sum(record.status == TrialStatus.TIMEOUT for record in records)
        case_records = {
            case.id: [record for record in records if record.case_id == case.id]
            for case in cases
        }
        judge_cost_usd = sum(
            grade.cost_usd for record in records for grade in record.grades
        )
        suite_summaries = {}
        for suite in {case.suite for case in cases}:
            suite_records = [record for record in records if record.suite == suite]
            suite_passed = sum(record.status == TrialStatus.PASSED for record in suite_records)
            suite_failed = sum(record.status == TrialStatus.FAILED for record in suite_records)
            suite_errors = len(suite_records) - suite_passed - suite_failed
            suite_summaries[suite] = SuiteSummary(
                trials=len(suite_records),
                passed=suite_passed,
                failed=suite_failed,
                errors=suite_errors,
                pass_rate=suite_passed / len(suite_records),
                average_score=sum(record.score for record in suite_records) / len(suite_records),
            )
        await dispatcher.drain()
        summary = RunSummary(
            run_id=active_run_id,
            evaluation_suite_id=self.suite.id,
            evaluation_suite_version=self.suite.version,
            started_at=started_at,
            total=len(records),
            cases=len(cases),
            repetitions=self.repetitions,
            passed=passed,
            failed=failed,
            errors=errors,
            timeouts=timeouts,
            pass_rate=passed / len(records),
            average_score=sum(record.score for record in records) / len(records),
            pass_at_k=sum(
                any(record.status == TrialStatus.PASSED for record in grouped)
                for grouped in case_records.values()
            )
            / len(cases),
            pass_power_k=sum(
                all(record.status == TrialStatus.PASSED for record in grouped)
                for grouped in case_records.values()
            )
            / len(cases),
            judge_cost_usd=judge_cost_usd,
            suites=suite_summaries,
            export_errors=tuple(dispatcher.errors),
            artifact_path=str(self.writer.path.resolve()),
        )
        await dispatcher.submit_summary(summary)
        await dispatcher.close()
        summary = summary.model_copy(update={"export_errors": tuple(dispatcher.errors)})
        await self.writer.append(summary)
        return summary

    @staticmethod
    async def _close_dispatcher(dispatcher: ExportDispatcher) -> None:
        close_task = asyncio.create_task(dispatcher.close())
        try:
            await asyncio.shield(close_task)
        except asyncio.CancelledError:
            await asyncio.shield(close_task)
            raise

    def _validate_sandbox(self, cases: Sequence[EvalCase]) -> None:
        isolation_required = self.sandbox_requirements.required or any(
            case.suite == SuiteType.SECURITY for case in cases
        )
        if isolation_required and self.sandbox_provider.name == "none":
            raise ValueError(
                "This evaluation requires a user-supplied SandboxProvider; "
                "set SandboxRequirements(required=False) only for trusted local graphs"
            )
        missing = self.sandbox_requirements.capabilities - self.sandbox_provider.capabilities
        if missing:
            raise ValueError(f"Sandbox provider lacks required capabilities: {sorted(missing)}")

    async def _run_trial(
        self, run_id: str, case: EvalCase, dataset_hash: str, repetition_index: int
    ) -> TrialRecord:
        trial_id = f"{run_id}:{case.id}:{repetition_index}:{uuid4()}"
        started_at = datetime.now(UTC)
        monotonic_start = time.monotonic()
        selected_graders = self._select_graders(case)
        tracked_metrics = (
            case.tracked_metrics or self.suite.tracked_metrics or DEFAULT_TRACKED_METRICS
        )
        provenance = Provenance(
            harness_version=self._harness_version(),
            code_revision=self.code_revision,
            dataset_hash=dataset_hash,
            target_hash=content_hash({"version": self.target.version}),
            evaluation_suite_id=self.suite.id,
            evaluation_suite_version=self.suite.version,
            prompt_hashes=self.prompt_hashes,
            grader_versions={grader.name: grader.version for grader in selected_graders},
            model=getattr(self.target, "model_name", None),
        )
        context = RunContext(run_id=run_id, trial_id=trial_id, budget=self.budget)
        result = None
        sandbox: SandboxSession | None = None
        sandbox_cleanup = SandboxCleanup()
        grades: tuple[Grade, ...] = ()
        status = TrialStatus.ERROR
        error_type = None
        error_message = None
        score = 0.0

        try:
            async with asyncio.timeout(self.budget.timeout_seconds):
                sandbox = await self.sandbox_provider.provision(case, context)
                if sandbox.provider != self.sandbox_provider.name:
                    raise ValueError("Sandbox provider returned mismatched identity")
                context = replace(context, sandbox=sandbox)
                with self.telemetry.operation(
                    "evaluation.target",
                    metric_prefix="evaluation.target",
                    span_attributes={
                        "evaluation.trial.id": trial_id,
                        "evaluation.target.version": self.target.version,
                    },
                    metric_attributes={
                        "evaluation.suite": case.suite.value,
                        "evaluation.target.version": self.target.version,
                    },
                ):
                    result = await self.target.execute(case, context)
                result = await self._collect_outcomes(case, result, context)
                grades = tuple(
                    await asyncio.gather(
                        *(
                            self._grade(grader, case, result, trial_id)
                            for grader in selected_graders
                        )
                    )
                )
                score = self._weighted_score(grades)
                required_passed = all(
                    grade.passed
                    for grade in grades
                    if grade.grader in self.grader_policy.required
                )
                status = (
                    TrialStatus.PASSED
                    if required_passed and score >= self.grader_policy.pass_threshold
                    else TrialStatus.FAILED
                )
        except TimeoutError:
            status = TrialStatus.TIMEOUT
            error_type = "TimeoutError"
            error_message = f"Trial exceeded {self.budget.timeout_seconds} seconds"
        except BudgetExceededError as error:
            status = TrialStatus.BUDGET_EXCEEDED
            error_type = type(error).__name__
            error_message = sanitize_text(str(error))
        except Exception as error:
            status = TrialStatus.ERROR
            error_type = type(error).__name__
            error_message = sanitize_text(str(error))[:2_000]
        finally:
            if sandbox is not None:
                try:
                    await self._destroy_sandbox(sandbox)
                    sandbox_cleanup = SandboxCleanup(attempted=True, succeeded=True)
                except Exception as cleanup_error:
                    status = TrialStatus.ERROR
                    error_type = "SandboxCleanupError"
                    error_message = sanitize_text(str(cleanup_error))[:2_000]
                    sandbox_cleanup = SandboxCleanup(
                        attempted=True,
                        succeeded=False,
                        error_type=type(cleanup_error).__name__,
                        error_message=error_message,
                    )

        duration_ms = max(0, int((time.monotonic() - monotonic_start) * 1000))
        record = TrialRecord(
            run_id=run_id,
            trial_id=trial_id,
            case_id=case.id,
            repetition_index=repetition_index,
            suite=case.suite,
            started_at=started_at,
            duration_ms=duration_ms,
            status=status,
            input_hash=content_hash(case.input),
            result=result,
            grades=grades,
            tracked_metrics=tracked_metrics,
            metrics=self._metric_values(result, duration_ms, tracked_metrics),
            score=score,
            error_type=error_type,
            error_message=error_message,
            sandbox=sandbox,
            sandbox_cleanup=sandbox_cleanup,
            provenance=provenance,
        )
        return self._bound_trial_record(record)

    def _bound_trial_record(self, record: TrialRecord) -> TrialRecord:
        artifact_bytes = len(record.model_dump_json(exclude_none=True).encode("utf-8"))
        if artifact_bytes <= self.budget.max_trial_artifact_bytes:
            return record
        bounded_sandbox = (
            record.sandbox.model_copy(update={"metadata": {"omitted": "artifact_limit"}})
            if record.sandbox is not None
            else None
        )
        bounded_provenance = record.provenance.model_copy(
            update={
                "prompt_hashes": {},
                "grader_versions": {},
                "model": None,
                "parameters_hash": None,
            }
        )
        return record.model_copy(
            update={
                "status": TrialStatus.BUDGET_EXCEEDED,
                "result": None,
                "grades": (),
                "metrics": {"latency": float(record.duration_ms)},
                "score": 0.0,
                "error_type": "ArtifactBudgetExceededError",
                "error_message": (
                    f"Trial artifact exceeded {self.budget.max_trial_artifact_bytes} bytes"
                ),
                "sandbox": bounded_sandbox,
                "provenance": bounded_provenance,
            }
        )

    async def _destroy_sandbox(self, sandbox: SandboxSession) -> None:
        cleanup_task = asyncio.create_task(self.sandbox_provider.destroy(sandbox))
        try:
            await asyncio.wait_for(
                asyncio.shield(cleanup_task),
                timeout=self.sandbox_cleanup_timeout_seconds,
            )
        except asyncio.CancelledError:
            try:
                await asyncio.wait_for(
                    asyncio.shield(cleanup_task),
                    timeout=self.sandbox_cleanup_timeout_seconds,
                )
            except TimeoutError:
                cleanup_task.cancel()
                await asyncio.gather(cleanup_task, return_exceptions=True)
            raise
        except TimeoutError:
            cleanup_task.cancel()
            await asyncio.gather(cleanup_task, return_exceptions=True)
            raise

    @staticmethod
    def _metric_values(
        result: TargetResult | None, duration_ms: int, selected: frozenset[str]
    ) -> dict[str, float]:
        if result is None:
            available = {"latency": float(duration_ms)}
        else:
            available = {
                "turns": float(
                    sum(event.kind == "model_end" for event in result.trajectory)
                ),
                "tool_calls": float(result.usage.tool_calls),
                "tokens": float(result.usage.input_tokens + result.usage.output_tokens),
                "latency": float(duration_ms),
                "cost": float(result.usage.cost_usd or 0),
                "loop_iterations": float(
                    len(result.loop.iterations) if result.loop is not None else 0
                ),
                "retrievals": float(len(result.retrievals)),
            }
        return {name: available[name] for name in selected if name in available}

    def _select_graders(self, case: EvalCase) -> tuple[Grader, ...]:
        requested = case.graders or self.suite.default_graders or frozenset(self._graders_by_name)
        selected_names = set(requested) | set(self.grader_policy.required)
        return tuple(
            grader for grader in self.graders if grader.name in selected_names
        )

    async def _collect_outcomes(
        self, case: EvalCase, result: TargetResult, context: RunContext
    ) -> TargetResult:
        if not self.outcome_collectors:
            return result

        async def collect(collector: OutcomeCollector) -> OutcomeObservation:
            with self.telemetry.operation(
                "evaluation.outcome_collector",
                metric_prefix="evaluation.outcome",
                span_attributes={
                    "evaluation.trial.id": context.trial_id,
                    "evaluation.outcome.collector": collector.name,
                    "evaluation.outcome.version": collector.version,
                },
                metric_attributes={
                    "evaluation.suite": case.suite.value,
                    "evaluation.outcome.collector": collector.name,
                },
            ):
                collected = await collector.collect(case, result, context)
            if isinstance(collected, OutcomeObservation):
                if collected.collector != collector.name or collected.version != collector.version:
                    raise ValueError("Outcome collector returned mismatched identity")
                observation = collected.model_copy(update={"state": sanitize(collected.state)})
            else:
                observation = OutcomeObservation(
                collector=collector.name,
                version=collector.version,
                state=sanitize(collected),
            )
            outcome_bytes = len(canonical_json(observation.state).encode("utf-8"))
            if outcome_bytes > self.budget.max_outcome_bytes:
                raise BudgetExceededError(
                    f"Outcome {collector.name!r} exceeded {self.budget.max_outcome_bytes} bytes"
                )
            return observation

        observations = await asyncio.gather(
            *(collect(collector) for collector in self.outcome_collectors)
        )
        return result.model_copy(update={"outcomes": (*result.outcomes, *observations)})

    async def _grade(
        self, grader: Grader, case: EvalCase, result: object, trial_id: str
    ) -> Grade:
        if not isinstance(result, TargetResult):
            raise TypeError("Target returned an invalid result")
        reserved_cost = float(getattr(grader, "maximum_cost_usd", 0.0))
        async with self._judge_cost_lock:
            if (
                self.budget.max_judge_cost_usd is not None
                and self._judge_cost_usd + reserved_cost
                > self.budget.max_judge_cost_usd
            ):
                raise BudgetExceededError(
                    "Run judge cost budget would be exceeded "
                    f"(${self.budget.max_judge_cost_usd:.4f})"
                )
            self._judge_cost_usd += reserved_cost
        try:
            with self.telemetry.operation(
                "evaluation.grader",
                metric_prefix="evaluation.grader",
                span_attributes={
                    "evaluation.trial.id": trial_id,
                    "evaluation.grader.name": grader.name,
                    "evaluation.grader.version": grader.version,
                },
                metric_attributes={
                    "evaluation.suite": case.suite.value,
                    "evaluation.grader.name": grader.name,
                },
            ):
                grade = await grader.grade(case, result)
        except Exception:
            async with self._judge_cost_lock:
                self._judge_cost_usd -= reserved_cost
            raise
        sanitized_evidence = sanitize(grade.evidence)
        evidence_bytes = len(canonical_json(sanitized_evidence).encode("utf-8"))
        if evidence_bytes > self.budget.max_grade_evidence_bytes:
            async with self._judge_cost_lock:
                self._judge_cost_usd -= reserved_cost
            raise BudgetExceededError(
                f"Grader {grader.name!r} evidence exceeded "
                f"{self.budget.max_grade_evidence_bytes} bytes"
            )
        grade = grade.model_copy(
            update={
                "reason": sanitize_text(grade.reason)[:2_000],
                "evidence": sanitized_evidence,
            }
        )
        async with self._judge_cost_lock:
            self._judge_cost_usd += grade.cost_usd - reserved_cost
            if (
                self.budget.max_judge_cost_usd is not None
                and self._judge_cost_usd > self.budget.max_judge_cost_usd
            ):
                raise BudgetExceededError("Model judge exceeded its declared maximum cost")
        return grade

    def _weighted_score(self, grades: tuple[Grade, ...]) -> float:
        weights = [self.grader_policy.weights.get(grade.grader, 1.0) for grade in grades]
        if any(weight < 0 for weight in weights):
            raise ValueError("Grader weights cannot be negative")
        total_weight = sum(weights)
        if total_weight == 0:
            raise ValueError("At least one grader weight must be positive")
        return sum(
            grade.score * weight for grade, weight in zip(grades, weights, strict=True)
        ) / total_weight

    @staticmethod
    def _harness_version() -> str:
        try:
            return importlib.metadata.version("langgraph-eval-harness")
        except importlib.metadata.PackageNotFoundError:
            return "development"
